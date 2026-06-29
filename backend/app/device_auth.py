"""CLI device authorization — OAuth 2.0 Device Authorization Grant (RFC 8628).

Lets an already-registered user sign a CLI in through the browser:

1. the CLI requests a device_code (returned once) + a short user_code;
2. the user, logged into the web app, approves the user_code;
3. the CLI polls and receives the same JWT a normal login issues.

Like an invitation token, the raw device_code is never stored — only its
SHA-256 hash. **Existing users only**: approval binds an already-authenticated
user and this never creates an account.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import create_cli_token
from .config import settings
from .models import DeviceAuthorization, User

# user_code uses an unambiguous alphabet (no 0/O/1/I) in two 4-char groups,
# e.g. "WDJB-MJHT" — easy to read off a screen and confirm against the terminal.
_USER_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_USER_CODE_GROUPS = 2
_USER_CODE_GROUP_LEN = 4


class DeviceAuthError(ValueError):
    """A terminal device-authorization failure (unknown/invalid code)."""


class AuthorizationPending(DeviceAuthError):
    """The user hasn't approved yet — the CLI should keep polling."""


class ExpiredToken(DeviceAuthError):
    """The device/user code has expired."""


class AlreadyUsed(DeviceAuthError):
    """A user_code that was already approved (approve step → 409)."""


def _now() -> datetime:
    # Naive UTC to match SQLite reads (avoids aware/naive comparison errors),
    # consistent with app.invites.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _make_user_code() -> str:
    groups = [
        "".join(secrets.choice(_USER_CODE_ALPHABET) for _ in range(_USER_CODE_GROUP_LEN))
        for _ in range(_USER_CODE_GROUPS)
    ]
    return "-".join(groups)


def create_device_code(
    db: Session,
    *,
    client_name: str | None = None,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> tuple[str, DeviceAuthorization]:
    """Start a flow. Returns (raw_device_code, row); the raw device_code is shown
    once to the CLI and never stored (only its hash is). The optional client
    context is recorded so the approval page can show where the sign-in came
    from."""
    device_code = secrets.token_urlsafe(32)
    user_code = _make_user_code()
    # user_code must be unique; retry on the rare collision.
    for _ in range(5):
        if db.scalar(
            select(DeviceAuthorization).where(DeviceAuthorization.user_code == user_code)
        ) is None:
            break
        user_code = _make_user_code()
    row = DeviceAuthorization(
        device_code_hash=_hash(device_code),
        user_code=user_code,
        status="pending",
        client_name=client_name,
        client_ip=client_ip,
        user_agent=user_agent,
        expires_at=_now() + timedelta(minutes=settings.device_code_ttl_minutes),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return device_code, row


def seconds_until_expiry(row: DeviceAuthorization) -> int:
    """Seconds left before the request expires (never negative)."""
    return max(0, int((row.expires_at - _now()).total_seconds()))


def lookup_pending_request(db: Session, *, user_code: str) -> DeviceAuthorization:
    """Find a still-pending request by user_code so the approval page can show its
    captured context before the user approves. Raises the same errors as
    approve_device_code (unknown/expired/already-used) so callers map them to the
    matching status codes."""
    row = db.scalar(
        select(DeviceAuthorization).where(
            DeviceAuthorization.user_code == user_code.strip().upper()
        )
    )
    if row is None:
        raise DeviceAuthError("invalid or expired code")
    if row.expires_at < _now():
        raise ExpiredToken("invalid or expired code")
    if row.status != "pending":
        raise AlreadyUsed("this request was already approved")
    return row


def approve_device_code(
    db: Session, *, user_code: str, user: User
) -> DeviceAuthorization:
    """Approve a pending user_code, binding it to an existing logged-in user.

    Raises DeviceAuthError (unknown/expired), ExpiredToken, or AlreadyUsed (the
    code was approved before). Never creates a user.
    """
    row = db.scalar(
        select(DeviceAuthorization).where(
            DeviceAuthorization.user_code == user_code.strip().upper()
        )
    )
    if row is None:
        raise DeviceAuthError("invalid or expired code")
    if row.expires_at < _now():
        raise ExpiredToken("invalid or expired code")
    if row.status != "pending":
        raise AlreadyUsed("this request was already approved")
    row.status = "approved"
    row.user_id = user.id
    row.approved_at = _now()
    db.commit()
    db.refresh(row)
    return row


def redeem_device_code(db: Session, *, device_code: str) -> str:
    """Poll step. Returns a fresh access token once the request is approved
    (one-time), else raises AuthorizationPending (still waiting) or a terminal
    DeviceAuthError/ExpiredToken."""
    row = db.scalar(
        select(DeviceAuthorization).where(
            DeviceAuthorization.device_code_hash == _hash(device_code)
        )
    )
    if row is None:
        raise DeviceAuthError("invalid device code")
    if row.status == "redeemed":
        raise DeviceAuthError("device code already used")
    if row.expires_at < _now():
        raise ExpiredToken("expired_token")
    if row.status != "approved":
        raise AuthorizationPending("authorization_pending")

    # The redeemed row now doubles as the CLI session; the token carries its id
    # as `sid` so it can be revoked from account settings.
    row.status = "redeemed"
    row.redeemed_at = _now()
    db.commit()
    return create_cli_token(row.user_id, row.id)
