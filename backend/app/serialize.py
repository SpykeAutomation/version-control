"""Build API response models from ORM objects (where a plain attribute copy
is not enough — e.g. a user's organization name needs a lookup)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import Organization, User
from .schemas import UserOut


def user_out(db: Session, user: User) -> UserOut:
    org = (
        db.get(Organization, user.organization_id)
        if user.organization_id is not None
        else None
    )
    return UserOut(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        organization=org.name if org is not None else None,
    )
