"""Organization invitations: owner-issued, single-use, expiring links.

The raw token goes only into the link the owner shares; the database stores
just its SHA-256 hash. Accepting requires the token *and* the invited email,
which also decides whether to create a new account or link an existing one.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import create_access_token, create_user
from .models import Invitation, Organization, User

INVITE_TTL_DAYS = 7


class InviteError(ValueError):
    """Raised when an invitation is invalid, used, expired, or mis-addressed."""


def _now() -> datetime:
    # Naive UTC to match what SQLite returns on read (avoids aware/naive compares).
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_invitation(
    db: Session,
    *,
    organization: Organization,
    email: str,
    invited_by: User,
    role: str = "member",
    ttl_days: int = INVITE_TTL_DAYS,
) -> tuple[str, Invitation]:
    """Create a pending invitation. Returns (raw_token, invite); the raw token
    is shown once (in the link) and never stored."""
    token = secrets.token_urlsafe(32)
    invite = Invitation(
        organization_id=organization.id,
        email=email.strip(),
        role=role or "member",
        token_hash=_hash_token(token),
        status="pending",
        invited_by=invited_by.id,
        expires_at=_now() + timedelta(days=ttl_days),
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return token, invite


def get_pending_invite(db: Session, token: str) -> Invitation:
    invite = db.scalar(
        select(Invitation).where(Invitation.token_hash == _hash_token(token))
    )
    if invite is None or invite.status != "pending":
        raise InviteError("invitation is invalid or already used")
    if invite.expires_at < _now():
        raise InviteError("invitation has expired")
    return invite


def accept_invitation(
    db: Session,
    *,
    token: str,
    email: str,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    password: Optional[str] = None,
) -> tuple[User, Optional[str]]:
    """Accept an invitation. Returns (user, access_token); the token is set only
    for a newly created account (an existing user logs in normally)."""
    invite = get_pending_invite(db, token)

    if email.strip().lower() != invite.email.strip().lower():
        raise InviteError("this invitation was sent to a different email")

    existing = db.scalar(
        select(User).where(func.lower(User.email) == email.strip().lower())
    )
    if existing is not None:
        existing.organization_id = invite.organization_id
        user = existing
        issued_token: Optional[str] = None
    else:
        if not (password and first_name and last_name):
            raise InviteError(
                "first name, last name, and password are required for a new account"
            )
        user = create_user(
            db,
            email=email.strip(),
            first_name=first_name,
            last_name=last_name,
            password=password,  # create_user enforces the password policy
            organization_id=invite.organization_id,
        )
        issued_token = create_access_token(user.id)

    invite.status = "accepted"
    invite.accepted_at = _now()
    invite.accepted_user_id = user.id
    db.commit()
    return user, issued_token
