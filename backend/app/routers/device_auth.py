"""CLI device-authorization endpoints (OAuth 2.0 Device Authorization Grant).

Three endpoints power the CLI's `spyke login`:

- ``POST /auth/device/code``    (public)        — start a flow
- ``POST /auth/device/approve`` (authenticated) — the web app approves a user_code
- ``POST /auth/device/token``   (public)        — the CLI polls for the token

Existing users only: approval binds an already-logged-in user (``current_user``)
and never creates an account. The device_code is stored only as a SHA-256 hash.
The token endpoint returns RFC-8628 reason codes (``authorization_pending`` /
``expired_token``) in the ``detail`` field, which the CLI understands.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import current_user
from ..config import settings
from ..db import get_db
from ..device_auth import (
    AlreadyUsed,
    AuthorizationPending,
    DeviceAuthError,
    ExpiredToken,
    approve_device_code,
    create_device_code,
    redeem_device_code,
)
from ..models import User
from ..ratelimit import device_rate_limit
from ..schemas import (
    DeviceApproveIn,
    DeviceApproveResult,
    DeviceCodeOut,
    DeviceTokenIn,
    TokenOut,
)

router = APIRouter(prefix="/auth/device", tags=["device auth"])


@router.post("/code", response_model=DeviceCodeOut)
def start_device_code(
    db: Session = Depends(get_db),
    _: None = Depends(device_rate_limit),
) -> DeviceCodeOut:
    """Public: begin a CLI login. Returns the device_code to poll with and the
    user_code + browser URL the user approves."""
    device_code, row = create_device_code(db)
    base = settings.web_app_url.rstrip("/")
    return DeviceCodeOut(
        device_code=device_code,
        user_code=row.user_code,
        verification_uri=f"{base}/cli-auth",
        verification_uri_complete=f"{base}/cli-auth?code={row.user_code}",
        interval=settings.device_poll_interval_seconds,
        expires_in=settings.device_code_ttl_minutes * 60,
    )


@router.post("/approve", response_model=DeviceApproveResult)
def approve_device(
    payload: DeviceApproveIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> DeviceApproveResult:
    """Authenticated: the web app's /cli-auth page calls this when the logged-in
    user approves the user_code their CLI is showing. Binds the request to that
    existing user (no account is created)."""
    try:
        approve_device_code(db, user_code=payload.user_code, user=user)
    except AlreadyUsed as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except DeviceAuthError as exc:  # invalid / expired
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return DeviceApproveResult()


@router.post("/token", response_model=TokenOut)
def poll_device_token(
    payload: DeviceTokenIn,
    db: Session = Depends(get_db),
    _: None = Depends(device_rate_limit),
) -> TokenOut:
    """Public: the CLI polls here. Returns the access token once approved; until
    then a 400 with detail ``authorization_pending`` (or ``expired_token``)."""
    try:
        token = redeem_device_code(db, device_code=payload.device_code)
    except AuthorizationPending:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "authorization_pending")
    except ExpiredToken:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "expired_token")
    except DeviceAuthError as exc:  # unknown / already-used
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return TokenOut(access_token=token)
