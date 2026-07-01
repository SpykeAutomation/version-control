"""Per-organization storage accounting via maintained counters.

Usage counts the **logical bytes of committed uploads** (the billing basis) —
deliberately not physical disk bytes, which shift with Git compression and
diff-cache eviction and require an O(disk) walk to measure. The truth per
project is `Project.used_bytes`; `Organization.used_bytes` is the org-level
aggregate kept in step so the quota gate can be one atomic UPDATE.

An upload **reserves** its bytes before the Git work starts and **releases**
them if that work fails; deleting a project gives its bytes back. For an org
the reserve is a single conditional UPDATE (`used_bytes + n <= limit`), so two
concurrent uploads can never both slip past the quota. A user with no org is
their own bucket, summed over their projects; that check-then-act path has a
tiny race under concurrent uploads, accepted for that edge case.
"""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session

from .config import settings
from .models import Organization, Project, User


def org_project_ids(db: Session, user: User) -> list[int]:
    """Every project that counts toward this user's org storage bucket."""
    if user.organization_id is not None:
        member_ids = select(User.id).where(
            User.organization_id == user.organization_id
        )
        owner_filter = Project.owner_id.in_(member_ids)
    else:
        owner_filter = Project.owner_id == user.id
    return list(db.scalars(select(Project.id).where(owner_filter)).all())


def bucket_limit_bytes(db: Session, user: User) -> int:
    """The caller's quota: the org's override if set, else the configured default."""
    if user.organization_id is not None:
        override = db.scalar(
            select(Organization.storage_limit_bytes).where(
                Organization.id == user.organization_id
            )
        )
        if override is not None:
            return override
    return settings.org_storage_limit_bytes


def bucket_used_bytes(db: Session, user: User) -> int:
    """Logical bytes the caller's bucket is using."""
    if user.organization_id is not None:
        return (
            db.scalar(
                select(Organization.used_bytes).where(
                    Organization.id == user.organization_id
                )
            )
            or 0
        )
    return (
        db.scalar(
            select(func.coalesce(func.sum(Project.used_bytes), 0)).where(
                Project.owner_id == user.id
            )
        )
        or 0
    )


def _quota_error() -> HTTPException:
    return HTTPException(
        status.HTTP_507_INSUFFICIENT_STORAGE,
        f"Organization storage limit of {settings.org_storage_limit_gb} GB reached",
    )


def reserve(db: Session, user: User, nbytes: int) -> None:
    """Reserve `nbytes` against the caller's quota, or raise 507.

    Org path: one conditional UPDATE — it only matches while the reservation
    still fits, so the gate is atomic under concurrency. Commits immediately so
    the reservation is visible to other requests before the (slow) Git work,
    and so no write lock is held across it.
    """
    if nbytes <= 0:
        return
    if user.organization_id is None:
        if bucket_used_bytes(db, user) + nbytes > bucket_limit_bytes(db, user):
            raise _quota_error()
        return
    result = db.execute(
        update(Organization)
        .where(
            Organization.id == user.organization_id,
            Organization.used_bytes + nbytes
            <= func.coalesce(
                Organization.storage_limit_bytes, settings.org_storage_limit_bytes
            ),
        )
        .values(used_bytes=Organization.used_bytes + nbytes)
    )
    db.commit()
    if result.rowcount == 0:
        raise _quota_error()


def release(db: Session, user: User, nbytes: int) -> None:
    """Give a failed upload's reservation back (org path only — an orgless
    reservation records nothing). Clamped at zero; never raises."""
    if nbytes <= 0 or user.organization_id is None:
        return
    _credit_org(db, user.organization_id, nbytes)
    db.commit()


def add_project_bytes(db: Session, project_id: int, nbytes: int) -> None:
    """Record a successful upload's bytes on its project (atomic increment so
    concurrent commits never lose an update). The caller commits."""
    if nbytes <= 0:
        return
    db.execute(
        update(Project)
        .where(Project.id == project_id)
        .values(used_bytes=Project.used_bytes + nbytes)
    )


def credit_project_deletion(db: Session, project: Project) -> None:
    """Give a deleted project's bytes back to its owner's org counter.

    Called before the delete is flushed; the caller commits. The org is looked
    up via the project owner (projects have no org column of their own).
    """
    if project.used_bytes <= 0:
        return
    org_id = db.scalar(
        select(User.organization_id).where(User.id == project.owner_id)
    )
    if org_id is not None:
        _credit_org(db, org_id, project.used_bytes)


def _credit_org(db: Session, org_id: int, nbytes: int) -> None:
    """Subtract from an org counter, clamped at zero (portable CASE, no MAX)."""
    db.execute(
        update(Organization)
        .where(Organization.id == org_id)
        .values(
            used_bytes=case(
                (Organization.used_bytes >= nbytes, Organization.used_bytes - nbytes),
                else_=0,
            )
        )
    )
