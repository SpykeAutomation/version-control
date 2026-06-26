"""Build API response models from ORM objects (where a plain attribute copy
is not enough — e.g. a user's organization name needs a lookup)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Organization, User
from .schemas import UserOut


def _user_out(user: User, org_name: str | None) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        organization=org_name,
        avatar=user.avatar,
    )


def user_out(db: Session, user: User) -> UserOut:
    org = (
        db.get(Organization, user.organization_id)
        if user.organization_id is not None
        else None
    )
    return _user_out(user, org.name if org is not None else None)


def users_out(db: Session, user_ids: list[int]) -> dict[int, UserOut]:
    """Serialize many users in a fixed number of queries (one for the users, one
    for their orgs) — the batched form for list endpoints, to avoid an N+1."""
    ids = {uid for uid in user_ids if uid is not None}
    if not ids:
        return {}
    users = db.scalars(select(User).where(User.id.in_(ids))).all()
    org_ids = {u.organization_id for u in users if u.organization_id is not None}
    org_names: dict[int, str] = {}
    if org_ids:
        org_names = {
            o.id: o.name
            for o in db.scalars(
                select(Organization).where(Organization.id.in_(org_ids))
            ).all()
        }
    return {
        u.id: _user_out(u, org_names.get(u.organization_id))
        for u in users
    }
