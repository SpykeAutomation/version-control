"""Login and the current-user endpoint.

Public self-service registration is intentionally not exposed. Accounts are
created by an admin via app.auth.create_user (see README); the route is also
blocked at the Caddy edge as a second layer.
"""
from __future__ import annotations

import re
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..auth import (
    create_access_token,
    current_user,
    hash_password,
    now_utc_naive,
    validate_password_strength,
    verify_password,
)
from ..config import settings
from ..db import get_db
from ..models import DeviceAuthorization, User
from ..ratelimit import (
    check_account_login,
    clear_login_failures,
    client_ip,
    login_rate_limit,
    record_login_failure,
)
from ..schemas import (
    CliSessionOut,
    PasswordChange,
    ProfileUpdate,
    TokenOut,
    UserOut,
)
from ..serialize import user_out

router = APIRouter(prefix="/auth", tags=["auth"])

# An avatar code is exactly 3 characters from a fixed alphabet; the frontend
# maps each position (base / colour / accessory) to an illustration.
_AVATAR_CODE = re.compile(r"[0-9A-Za-z]{3}")


@router.post("/login", response_model=TokenOut)
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
    _: None = Depends(login_rate_limit),
) -> TokenOut:
    # Account lockout first: a locked account is rejected before the
    # (CPU-expensive) password verify.
    check_account_login(form.username)
    # OAuth2 form uses "username"; we treat it as the email.
    user = db.scalar(select(User).where(User.email == form.username))
    # A soft-deleted account can't log in (kept generic so deletion isn't probeable).
    if (
        user is None
        or user.deleted_at is not None
        or not verify_password(form.password, user.password_hash)
    ):
        record_login_failure(form.username)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    clear_login_failures(form.username)
    return TokenOut(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> UserOut:
    return user_out(db, user)


@router.patch("/me", response_model=UserOut)
def update_me(
    payload: ProfileUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> UserOut:
    """Update your own profile: first/last name and avatar code. Email and org
    membership are not editable here."""
    if payload.first_name is not None:
        user.first_name = payload.first_name.strip()
    if payload.last_name is not None:
        user.last_name = payload.last_name.strip()
    if payload.avatar is not None:
        if not _AVATAR_CODE.fullmatch(payload.avatar):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "avatar must be exactly 3 alphanumeric characters",
            )
        user.avatar = payload.avatar
    db.commit()
    db.refresh(user)
    return user_out(db, user)


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChange,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Change your password. Requires the current password and enforces the
    same strength policy as account creation."""
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Current password is incorrect")
    try:
        validate_password_strength(payload.new_password)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me/sessions", response_model=list[CliSessionOut])
def list_cli_sessions(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[CliSessionOut]:
    """Your active CLI logins, newest first — what account settings lists with a
    revoke button. Each redeemed-and-not-revoked device authorization is one
    session."""
    rows = db.scalars(
        select(DeviceAuthorization)
        .where(
            DeviceAuthorization.user_id == user.id,
            DeviceAuthorization.status == "redeemed",
            DeviceAuthorization.revoked_at.is_(None),
        )
        .order_by(DeviceAuthorization.redeemed_at.desc())
    ).all()
    current_sid = getattr(user, "current_session_id", None)
    lifetime = timedelta(days=settings.cli_token_expire_days)
    out = []
    for row in rows:
        login_at = row.redeemed_at or row.created_at
        out.append(
            CliSessionOut(
                id=row.id,
                client_name=row.client_name,
                client_ip=row.client_ip,
                created_at=login_at,
                last_used_at=row.last_used_at,
                expires_at=login_at + lifetime,
                current=(row.id == current_sid),
            )
        )
    return out


@router.delete("/me/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_cli_session(
    session_id: int,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Revoke one of your own CLI logins. The token bound to it stops working on
    its next request. Idempotent; only your own sessions are visible."""
    row = db.get(DeviceAuthorization, session_id)
    if row is None or row.user_id != user.id or row.status != "redeemed":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    if row.revoked_at is None:
        row.revoked_at = now_utc_naive()
        audit.record(
            db,
            action="cli.session.revoked",
            actor_id=user.id,
            target_user_id=user.id,
            target_type="cli_session",
            target_id=row.id,
            summary=f"revoked CLI session: {row.client_name or 'unknown client'}",
            ip=client_ip(request),
        )
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
