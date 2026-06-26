"""Login and the current-user endpoint.

Public self-service registration is intentionally not exposed. Accounts are
created by an admin via app.auth.create_user (see README); the route is also
blocked at the Caddy edge as a second layer.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import (
    create_access_token,
    current_user,
    hash_password,
    validate_password_strength,
    verify_password,
)
from ..db import get_db
from ..models import User
from ..ratelimit import login_rate_limit
from ..schemas import PasswordChange, ProfileUpdate, TokenOut, UserOut
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
    # OAuth2 form uses "username"; we treat it as the email.
    user = db.scalar(select(User).where(User.email == form.username))
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
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
