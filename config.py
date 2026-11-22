"""LitPilot runtime configuration.

Everything that a demo must be able to change without touching code lives here.
Values come from environment (.env) with safe defaults so the app always boots.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

# ---------------------------------------------------------------- paths
# LITPILOT_DATA points data/ somewhere else (a mounted volume, a tmpfs). On Fly.io
# that is what keeps traces across redeploys; on Hugging Face Spaces the filesystem
# is ephemeral and this stays unset.
_DATA_ENV = os.getenv("LITPILOT_DATA", "").strip()
DATA_DIR = Path(_DATA_ENV).expanduser() if _DATA_ENV else ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
PDF_DIR = CACHE_DIR / "pdf"
SEARCH_DIR = CACHE_DIR / "search"
TEXT_DIR = CACHE_DIR / "text"
RUNS_DIR = DATA_DIR / "runs"
WEB_DIR = ROOT / "web"

for _p in (DATA_DIR, CACHE_DIR, PDF_DIR, SEARCH_DIR, TEXT_DIR, RUNS_DIR):
    _p.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- model
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
LLM_TIMEOUT_S = float(os.getenv("LITPILOT_LLM_TIMEOUT", "90"))
LLM_TEMPERATURE = float(os.getenv("LITPILOT_LLM_TEMPERATURE", "0.2"))

# ---------------------------------------------------------------- pipeline
PAPER_LIMIT = int(os.getenv("LITPILOT_PAPER_LIMIT", "5"))
RECENT_YEARS = int(os.getenv("LITPILOT_RECENT_YEARS", "5"))
# how much of a paper we hand to the extraction model, in characters
EXTRACT_CHAR_BUDGET = int(os.getenv("LITPILOT_EXTRACT_CHARS", "14000"))
HTTP_TIMEOUT_S = float(os.getenv("LITPILOT_HTTP_TIMEOUT", "30"))
FETCH_TIMEOUT_S = float(os.getenv("LITPILOT_FETCH_TIMEOUT", "25"))
MAX_EXTRACT_RETRY = int(os.getenv("LITPILOT_MAX_EXTRACT_RETRY", "2"))

# Offline / no-key mode: the whole trace pipeline still runs.
# Without a key, mock is the only honest default — a run that cannot call a model
# should not pretend to be a live run.
_MOCK_ENV = os.getenv("LITPILOT_MOCK", "").strip().lower()
DEFAULT_MOCK = _MOCK_ENV in ("1", "true", "yes") if _MOCK_ENV else not DEEPSEEK_API_KEY

# 分享口令：设了就要求 ?k=<口令>（首访写 cookie）。本地演示留空；
# 开公网隧道时必须设——否则任何人拿到链接都能烧你的 API 额度。
SHARE_TOKEN = os.getenv("LITPILOT_SHARE_TOKEN", "").strip()

# 公网部署的额度闸。链接一旦被转发，任何人都能点"运行"，每一次真实运行都在花
# 你的 DeepSeek 额度：所以进程内按天计数，超了就 429 而不是默默烧钱。
# 演示前几天可以调大；比赛当天建议 ≥30（一天几十次足够反复彩排）。
RUN_BUDGET = int(os.getenv("LITPILOT_RUN_BUDGET", "40"))
# 免费档只有 2 vCPU，同时跑两个真实任务（每个 60s+）会互相拖慢并触发 fetch 超时。
MAX_CONCURRENT = int(os.getenv("LITPILOT_MAX_CONCURRENT", "1"))


def llm_ready() -> bool:
    """True when a real model call is possible."""
    return bool(DEEPSEEK_API_KEY)
