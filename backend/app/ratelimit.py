"""Small in-process rate limiter — no external dependency.

The pilot runs a single web worker, so an in-memory sliding window shared
across that worker's threads (guarded by a lock) is enough. Requests reach the
app only via Caddy, so the real client IP is in X-Forwarded-For; we key on that
and fall back to the socket peer. Used as a FastAPI dependency on sensitive
endpoints (login, plus the public invite preview/accept) to blunt brute-force
and request floods. Each endpoint family gets its own scoped bucket so their
counters don't bleed into each other.

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


def _enforce(scope: str, request: Request, limit: int, window: int, message: str) -> None:
    """Sliding-window check for one (scope, client IP) pair. Raises 429 with a
    Retry-After header once the window is full."""
    _enforce_key(f"{scope}:{client_ip(request)}", limit, window, message)


def _enforce_key(key: str, limit: int, window: int, message: str) -> None:
    """The sliding window itself, for any bucket key (an IP or an account)."""
    now = time.monotonic()
    with _lock:
        bucket = _hits[key]
        while bucket and now - bucket[0] > window:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = int(window - (now - bucket[0])) + 1
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                message,
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)


def login_rate_limit(request: Request) -> None:
    """Dependency: cap login attempts per client IP within a time window.

    This is only the coarse flood guard (and per-IP is spoofable via
    X-Forwarded-For anyway); the per-account lockout below is the real
    anti-guessing control."""
    _enforce(
        "login",
        request,
        settings.login_rate_max,
        settings.login_rate_window_seconds,
        "Too many login attempts; please try again later.",
    )


# ---- Per-account login lockout ----------------------------------------------
# Keyed by the submitted email (normalized), not the client IP, so it works
# against distributed guessing and never punishes a whole site behind one NAT.
# Called from inside the login handler (not as a dependency) because only the
# handler knows whether the attempt failed.

_account_failures: dict[str, deque[float]] = defaultdict(deque)


def _account_key(email: str) -> str:
    return email.strip().casefold()


def check_account_login(email: str) -> None:
    """Reject with 429 when this account has too many recent failed logins.

    Checked *before* the password verify, so a locked account costs no bcrypt
    work. Unknown emails are tracked like real ones so lockout behavior can't
    be used to probe whether an account exists."""
    key = _account_key(email)
    window = settings.login_account_window_seconds
    now = time.monotonic()
    with _lock:
        bucket = _account_failures[key]
        while bucket and now - bucket[0] > window:
            bucket.popleft()
        if not bucket:
            del _account_failures[key]  # keep the map from growing unbounded
            return
        if len(bucket) >= settings.login_account_max:
            retry_after = int(window - (now - bucket[0])) + 1
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many failed login attempts for this account; "
                "please try again later.",
                headers={"Retry-After": str(retry_after)},
            )


def record_login_failure(email: str) -> None:
    """A wrong password (or unknown email) counts toward the account lockout."""
    with _lock:
        _account_failures[_account_key(email)].append(time.monotonic())


def clear_login_failures(email: str) -> None:
    """A successful login forgives the account's earlier failures."""
    with _lock:
        _account_failures.pop(_account_key(email), None)


def invite_rate_limit(request: Request) -> None:
    """Dependency: cap invite preview/accept calls per client IP. Both the GET
    preview and the POST accept leak whether a token is valid, so a shared
    per-IP budget blunts token enumeration and brute-forcing the accept step."""
    _enforce(
        "invite",
        request,
        settings.invite_rate_max,
        settings.invite_rate_window_seconds,
        "Too many invitation requests; please try again later.",
    )


def member_search_rate_limit(user_id: int) -> None:
    """Cap member-candidate searches per account within a time window.

    The endpoint substring-matches over the org's user directory, so it
    enumerates personal data; keyed on the authenticated account (not the IP)
    so one account can't spray queries and a whole plant behind one NAT is
    never punished collectively. Called from inside the handler, after the
    membership check has established who is asking."""
    _enforce_key(
        f"member-search:{user_id}",
        settings.member_search_rate_max,
        settings.member_search_rate_window_seconds,
        "Too many member searches; please try again later.",
    )


def device_rate_limit(request: Request) -> None:
    """Dependency: cap the public CLI device-auth calls (code request + token
    polling) per client IP, so the device endpoints can't be flooded. Roomier
    than login since a single login legitimately polls several times."""
    _enforce(
        "device",
        request,
        settings.device_rate_max,
        settings.device_rate_window_seconds,
        "Too many device-authorization requests; please try again later.",
    )
