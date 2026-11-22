"""Build a folder that can be pushed to a Hugging Face Space as-is.

    python scripts/hf_space_export.py        -> dist/hf-space/

Why a separate folder instead of pushing the repo root: a Space *requires* its card
metadata in README.md YAML frontmatter, and our README is a normal project README.
Rather than keep two READMEs in sync (they always drift), this script prepends the
frontmatter to the real README — one source of truth, valid on both sides.

Hugging Face reads: Dockerfile, requirements.txt, README.md (frontmatter), app_port.
Everything else is just files in the image.

    cd dist/hf-space
    git init -b main && git add -A
    git commit -m "LitPilot Space"
    git remote add space https://huggingface.co/spaces/<user>/<space>
    git push space main

Pushing prompts for a token with `write` scope — that token is a password: it goes
into the credential prompt, never into a file in this repo.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dist" / "hf-space"

INCLUDE_DIRS = ["tools", "web", "scripts", "docs"]
INCLUDE_FILES = ["Dockerfile", "requirements.txt", "fly.toml", "render.yaml", ".env.example", ".gitignore"]
EXCLUDE_DIRS = {"__pycache__", "data", "dist", ".packages", ".wheels", ".tmppip", ".git"}

FRONTMATTER = """---
title: LitPilot
emoji: 📚
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: 文献综述智能体：每条结论都能回原文核对
---

"""


def _reset(out: Path) -> None:
    """清空导出目录里的文件，但**留下 .git**。

    这条很重要：Space 就是一个 git 仓库，`dist/hf-space/.git` 里有你的提交历史和
    remote。早先这里用的是 shutil.rmtree(OUT)，重跑一次导出就把历史连 remote 一起
    删了——改一次代码就得重新 git init、重新配 remote，还丢掉了"哪一版跑过演示"的
    记录。留下 .git 之后，导出 = 覆盖文件，然后 git add/commit/push 就完事。
    """
    out.mkdir(parents=True, exist_ok=True)
    for child in out.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def main() -> int:
    had_git = (OUT / ".git").exists()
    _reset(OUT)

    for name in INCLUDE_FILES:
        src = ROOT / name
        if src.exists():
            shutil.copy2(src, OUT / name)
    for d in INCLUDE_DIRS:
        for src in sorted((ROOT / d).rglob("*")):
            if not src.is_file() or (set(src.parts) & EXCLUDE_DIRS):
                continue
            rel = src.relative_to(ROOT)
            (OUT / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, OUT / rel)
    for src in sorted(ROOT.glob("*.py")):
        shutil.copy2(src, OUT / src.name)

    body = (ROOT / "README.md").read_text(encoding="utf-8")
    (OUT / "README.md").write_text(FRONTMATTER + body, encoding="utf-8")

    # 一键推送脚本也带过去，用户在那个目录里打 `.\push.ps1` 就能提交+推送
    # （终端里手打长命令已经出过 "gi add -Agit commi" 这种字符被吞的事故）。
    # push.cmd 是给"执行策略禁止运行未签名 ps1"的机器准备的 —— cmd 不受执行策略管。
    for src_name, dst_name in (
        ("push_space.ps1", "push.ps1"),
        ("push_space.cmd", "push.cmd"),
        ("push_github.cmd", "push_github.cmd"),
    ):
        src = ROOT / "scripts" / src_name
        if src.exists():
            shutil.copy2(src, OUT / dst_name)

    # The Space must not carry our key; the platform injects secrets itself.
    if (OUT / ".env").exists():
        (OUT / ".env").unlink()

    files = sorted(
        p.relative_to(OUT).as_posix()
        for p in OUT.rglob("*")
        if p.is_file() and ".git" not in p.parts
    )
    print(f"{OUT}  {len(files)} files")
    for f in files[:8]:
        print("  ", f)
    if len(files) > 8:
        print(f"   ... {len(files) - 8} more")
    if had_git:
        print("git 历史已保留。下一步：")
        print("  cd dist\\hf-space && git add -A && git commit -m \"update\" && git push space main")
    else:
        print("下一步：git init -b main / git add -A / git commit / git remote add space ... / git push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
