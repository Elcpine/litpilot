"""LLM access (DeepSeek, OpenAI-compatible).

Only two things matter for this project:
  1. JSON mode must be reliable -> we re-ask with the parse error attached.
  2. A failure must be visible, never silently swallowed -> LLMError carries why.
"""

from __future__ import annotations

import json
import re

import httpx

from config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    LLM_TEMPERATURE,
    LLM_TIMEOUT_S,
    llm_ready,
)

__all__ = ["LLMError", "chat_json", "llm_ready", "model_name", "reset_usage", "usage"]

# 官方价（USD / 1M tokens，2026-11 版 deepseek-flash）：
#   输入 cache hit  $0.003 平 / $0.006 峰
#   输入 cache miss $0.15  平 / $0.30  峰
#   输出            $0.6   平 / $1.2   峰
# 峰时 = UTC 01:00-04:00 与 06:00-10:00 的工作日（北京时间 09-12、14-18）。
# 峰时正好覆盖比赛演示时段，所以预算按峰价算（宁可高估）。
PRICE_USD = {
    "hit": 0.006,
    "miss": 0.30,
    "out": 1.20,
}

USAGE: dict[str, int] = {
    "calls": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "cache_hit_tokens": 0,
    "cache_miss_tokens": 0,
}


class LLMError(RuntimeError):
    pass


def reset_usage() -> None:
    """每轮开始清零，这样 metrics 里的成本是"这一轮"的，不是进程累计。"""
    for k in USAGE:
        USAGE[k] = 0


def usage() -> dict:
    """返回本轮用量与按官方峰价估算的美元成本。"""
    hit = USAGE["cache_hit_tokens"]
    miss = USAGE["cache_miss_tokens"]
    if hit + miss == 0:  # 老接口不返回缓存明细时，全部按 miss 算（高估）
        miss = USAGE["prompt_tokens"]
    cost = (
        hit / 1_000_000 * PRICE_USD["hit"]
        + miss / 1_000_000 * PRICE_USD["miss"]
        + USAGE["completion_tokens"] / 1_000_000 * PRICE_USD["out"]
    )
    return {
        "calls": USAGE["calls"],
        "tokens": USAGE["prompt_tokens"] + USAGE["completion_tokens"],
        "prompt_tokens": USAGE["prompt_tokens"],
        "completion_tokens": USAGE["completion_tokens"],
        "cache_hit_tokens": hit,
        "cost_usd": round(cost, 6),
    }


def _record_usage(body: dict) -> None:
    u = body.get("usage") or {}
    USAGE["calls"] += 1
    USAGE["prompt_tokens"] += int(u.get("prompt_tokens") or 0)
    USAGE["completion_tokens"] += int(u.get("completion_tokens") or 0)
    USAGE["cache_hit_tokens"] += int(u.get("prompt_cache_hit_tokens") or 0)
    USAGE["cache_miss_tokens"] += int(u.get("prompt_cache_miss_tokens") or 0)


def model_name() -> str:
    return DEEPSEEK_MODEL


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise LLMError(f"model did not return JSON: {text[:200]}")


async def chat_json(
    system: str,
    user: str,
    *,
    retries: int = 2,
    temperature: float | None = None,
) -> dict:
    if not llm_ready():
        raise LLMError("DEEPSEEK_API_KEY is not configured")

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": LLM_TEMPERATURE if temperature is None else temperature,
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=LLM_TIMEOUT_S) as client:
                r = await client.post(
                    f"{DEEPSEEK_BASE_URL}/chat/completions", json=payload, headers=headers
                )
            if r.status_code == 429:
                raise LLMError("rate limited (429)")
            if r.status_code >= 500:
                raise LLMError(f"upstream {r.status_code}")
            if r.status_code != 200:
                raise LLMError(f"http {r.status_code}: {r.text[:200]}")
            body = r.json()
            _record_usage(body)
            content = body["choices"][0]["message"]["content"]
            return _extract_json(content)
        except Exception as exc:  # noqa: BLE001 - every failure must be retried or surfaced
            last_err = exc
            if attempt < retries:
                import asyncio

                await asyncio.sleep(1.5 * (attempt + 1))
                continue
    raise LLMError(str(last_err))
