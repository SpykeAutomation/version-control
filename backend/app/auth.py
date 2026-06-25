"""Password hashing, JWT issuing, and the current-user dependency."""
from __future__ import annotations

import datetime as dt
import re

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import Organization, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    # bcrypt only considers the first 72 bytes; truncating keeps it explicit.
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:72], hashed.encode())
    except ValueError:
        return False


def validate_password_strength(password: str) -> None:
    """Raise ValueError if the password fails the policy.

    Policy: at least 12 characters, with at least one lowercase letter, one
    uppercase letter, and one digit. Used by the register schema and by the
    admin account-creation command, so both enforce the same rule.
    """
    if len(password) < 12:
        raise ValueError("password must be at least 12 characters long")
    if not re.search(r"[a-z]", password):
        raise ValueError("password must contain a lowercase letter")
    if not re.search(r"[A-Z]", password):
        raise ValueError("password must contain an uppercase letter")
    if not re.search(r"[0-9]", password):
        raise ValueError("password must contain a digit")


def create_user(
    db: Session,
    *,
    email: str,
    first_name: str,
    last_name: str,
    password: str,
    organization: str | None = None,
) -> User:
    """Create an account (admin path; public registration is closed).

    Enforces the password policy and optionally links the user to an
    organization by name, creating that organization if it does not exist.
    Raises ValueError on a weak password or a duplicate email.
    """
    validate_password_strength(password)
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise ValueError(f"email already registered: {email}")

    organization_id = None
    if organization:
        org = db.scalar(select(Organization).where(Organization.name == organization))
        if org is None:
            org = Organization(name=organization)
            db.add(org)
            db.flush()
        organization_id = org.id

    user = User(
        email=email,
        first_name=first_name,
        last_name=last_name,
        password_hash=hash_password(password),
        organization_id=organization_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_access_token(user_id: int) -> str:
    expire = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
        minutes=settings.jwt_expire_minutes
    )
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise credentials_error
    user = db.get(User, user_id)
    if user is None:
        raise credentials_error
    return user
