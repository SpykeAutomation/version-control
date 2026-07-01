FROM python:3.12-slim

# git is required at runtime: each project is stored as a real Git repository.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /code

COPY requirements.txt requirements-app.txt ./
RUN pip install --no-cache-dir -r requirements-app.txt

COPY . .

# Persistent data (SQLite DB + per-project Git repos) lives here; mount a
# volume at /data in production so it survives restarts and deploys.
ENV PLCVC_DATA_DIR=/data
EXPOSE 8000

# Single worker: Git operations share a working tree per project and are
# serialized by a per-project lock (see app/storage.py); on a 1-vCPU host more
# workers add no CPU throughput anyway.
# --limit-concurrency sheds load: once that many connections are in flight,
# new ones get a fast 503 instead of queueing until the box tips over. Sized
# for a small (1 vCPU / 2 GB) host; override via env without a rebuild.
# Shell form so ${PORT} is honored on hosts that inject it (e.g. Render),
# defaulting to 8000 locally and under docker-compose.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 \
    --limit-concurrency ${UVICORN_LIMIT_CONCURRENCY:-64}
