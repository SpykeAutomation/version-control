"""Small in-process rate limiter — no external dependency.

The pilot runs a single web worker, so an in-memory sliding window shared
across that worker's threads (guarded by a lock) is enough. Requests reach the
app only via Caddy, so the real client IP is in X-Forwarded-For; we key on that
and fall back to the socket peer. Used as a FastAPI dependency on sensitive
endpoints (currently login) to blunt brute-force and request floods.

Scaling note: move this to a shared store (Redis / Postgres) before running
more than one worker, or the counters won't be shared across processes.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from .config import settings

_hits: dict[str, deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def login_rate_limit(request: Request) -> None:
    """Dependency: cap login attempts per client IP within a time window."""
    limit = settings.login_rate_max
    window = settings.login_rate_window_seconds
    ip = client_ip(request)
    now = time.monotonic()
    with _lock:
        bucket = _hits[ip]
        while bucket and now - bucket[0] > window:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = int(window - (now - bucket[0])) + 1
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many login attempts; please try again later.",
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)
