"""Login and the current-user endpoint.

Public self-service registration is intentionally not exposed. Accounts are
created by an admin via app.auth.create_user (see README); the route is also
blocked at the Caddy edge as a second layer.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import create_access_token, current_user, verify_password
from ..db import get_db
from ..models import User
from ..ratelimit import login_rate_limit
from ..schemas import TokenOut, UserOut
from ..serialize import user_out

router = APIRouter(prefix="/auth", tags=["auth"])


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
