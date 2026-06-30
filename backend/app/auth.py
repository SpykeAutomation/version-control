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
from .models import DeviceAuthorization, Organization, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# Refresh a CLI session's last_used_at at most this often, so we don't add a DB
# write to every authenticated request.
_SESSION_TOUCH_INTERVAL = dt.timedelta(minutes=5)


def now_utc_naive() -> dt.datetime:
    """Naive UTC 'now'. Timestamps are stored and compared naive across the app
    (SQLite returns naive datetimes); see app.device_auth for the rationale."""
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


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
    organization_id: int | None = None,
) -> User:
    """Create an account (admin / invite-acceptance path).

    Enforces the password policy. Organization membership is set by id (None for
    none); it is never derived from a user-supplied name — a user joins an org
    only by accepting an owner's invitation (app.invites) or via
    create_org_with_owner for bootstrapping. Raises ValueError on a weak
    password or a duplicate email.
    """
    validate_password_strength(password)
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise ValueError(f"email already registered: {email}")

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


def create_org_with_owner(
    db: Session,
    *,
    name: str,
    owner_email: str,
    owner_first: str,
    owner_last: str,
    owner_password: str,
) -> tuple[Organization, User]:
    """Bootstrap a company: create its owner account and the organization they
    own, and map the owner into it. Admin path; members then join by invitation
    only."""
    if db.scalar(select(Organization).where(Organization.name == name)) is not None:
        raise ValueError(f"organization already exists: {name}")
    owner = create_user(
        db, email=owner_email, first_name=owner_first,
        last_name=owner_last, password=owner_password,
    )
    org = Organization(name=name, owner_id=owner.id)
    db.add(org)
    db.flush()
    owner.organization_id = org.id
    db.commit()
    db.refresh(org)
    db.refresh(owner)
    return org, owner


def create_access_token(user_id: int) -> str:
    """A normal web-login token (stateless, one week). CLI logins use
    create_cli_token instead."""
    expire = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
        minutes=settings.jwt_expire_minutes
    )
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_cli_token(user_id: int, session_id: int) -> str:
    """A CLI access token bound to a device session (the DeviceAuthorization row
    id). Long-lived but capped, and carries `sid` so the session can be revoked
    from account settings; `typ` distinguishes it from a web login."""
    expire = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
        days=settings.cli_token_expire_days
    )
    payload = {"sub": str(user_id), "exp": expire, "sid": session_id, "typ": "cli"}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _touch_session(db: Session, session: DeviceAuthorization) -> None:
    """Record CLI activity, but write at most every few minutes."""
    now = now_utc_naive()
    if session.last_used_at is None or now - session.last_used_at > _SESSION_TOUCH_INTERVAL:
        session.last_used_at = now
        db.commit()


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

    # CLI tokens are bound to a revocable session; the web token has no `sid`.
    session_id = payload.get("sid")
    if session_id is not None:
        session = db.get(DeviceAuthorization, session_id)
        if (
            session is None
            or session.user_id != user_id
            or session.status != "redeemed"
            or session.revoked_at is not None
        ):
            raise credentials_error
        _touch_session(db, session)

    user = db.get(User, user_id)
    # A soft-deleted account is rejected immediately, web or CLI.
    if user is None or user.deleted_at is not None:
        raise credentials_error
    # Lets endpoints flag "this is the session you're using" without re-decoding.
    user.current_session_id = session_id
    return user
