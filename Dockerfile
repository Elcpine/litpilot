# LitPilot — one container, serves the API and the static UI.
#
# Used by both deploy targets: Hugging Face Spaces (free CPU, sets PORT=7860) and
# Fly.io (fly.toml sets PORT=8080). No build step, no node, no compile toolchain —
# every dependency is pure Python, which is why the image stays small.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Hugging Face Spaces runs containers as uid 1000. If /app stayed root-owned, the
# first `mkdir data/runs` in config.py would raise PermissionError and the Space
# would look "broken" with no useful log line. So: create that uid ourselves and
# hand it the tree.
RUN useradd --create-home --uid 1000 user && chown -R user:user /app
USER user

EXPOSE 7860

# Shell form on purpose: ${PORT} must expand at runtime (HF=7860, Fly=8080).
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-7860} --proxy-headers --forwarded-allow-ips='*'"]
