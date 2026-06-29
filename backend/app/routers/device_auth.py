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

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
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
    lookup_pending_request,
    redeem_device_code,
    seconds_until_expiry,
)
from .. import audit
from ..models import User
from ..ratelimit import client_ip, device_rate_limit
from ..schemas import (
    DeviceApproveIn,
    DeviceApproveResult,
    DeviceCodeIn,
    DeviceCodeOut,
    DeviceInfoOut,
    DeviceTokenIn,
    TokenOut,
)

router = APIRouter(prefix="/auth/device", tags=["device auth"])


@router.post("/code", response_model=DeviceCodeOut)
def start_device_code(
    request: Request,
    payload: DeviceCodeIn | None = Body(default=None),
    db: Session = Depends(get_db),
    _: None = Depends(device_rate_limit),
) -> DeviceCodeOut:
    """Public: begin a CLI login. Returns the device_code to poll with and the
    user_code + browser URL the user approves. Records the CLI's reported context
    (client label, IP, user-agent) so the approval page can show where the
    sign-in came from."""
    device_code, row = create_device_code(
        db,
        client_name=payload.client_name if payload else None,
        client_ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    base = settings.web_app_url.rstrip("/")
    return DeviceCodeOut(
        device_code=device_code,
        user_code=row.user_code,
        verification_uri=f"{base}/cli-auth",
        verification_uri_complete=f"{base}/cli-auth?code={row.user_code}",
        interval=settings.device_poll_interval_seconds,
        expires_in=settings.device_code_ttl_minutes * 60,
    )


@router.get("/info", response_model=DeviceInfoOut)
def device_request_info(
    user_code: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    _: None = Depends(device_rate_limit),
) -> DeviceInfoOut:
    """Authenticated: the /cli-auth page reads the pending request's context
    (client label, originating IP, age) so it can show the user *what* they're
    about to approve before they confirm. A read-only lookup — it never changes
    state."""
    try:
        row = lookup_pending_request(db, user_code=user_code)
    except AlreadyUsed as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except DeviceAuthError as exc:  # invalid / expired
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return DeviceInfoOut(
        user_code=row.user_code,
        client_name=row.client_name,
        client_ip=row.client_ip,
        requested_at=row.created_at,
        expires_in=seconds_until_expiry(row),
    )


@router.post("/approve", response_model=DeviceApproveResult)
def approve_device(
    payload: DeviceApproveIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    _: None = Depends(device_rate_limit),
) -> DeviceApproveResult:
    """Authenticated: the web app's /cli-auth page calls this when the logged-in
    user approves the user_code their CLI is showing. Binds the request to that
    existing user (no account is created). Rate-limited per IP so the short
    user_code can't be brute-forced through this endpoint."""
    try:
        row = approve_device_code(db, user_code=payload.user_code, user=user)
    except AlreadyUsed as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except DeviceAuthError as exc:  # invalid / expired
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    audit.record(
        db,
        action="cli.session.approved",
        actor_id=user.id,
        target_user_id=user.id,
        target_type="cli_session",
        target_id=row.id,
        summary=f"approved CLI login: {row.client_name or 'unknown client'}",
        ip=client_ip(request),
    )
    db.commit()
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
