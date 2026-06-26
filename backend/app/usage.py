"""Per-organization on-disk storage accounting.

Usage counts both a project's Git repository and its cached diffs (the chosen
billing basis). A project belongs to its owner's organization; an owner with no
organization is their own one-person bucket. The tree is walked live on each
upload — fine at pilot scale, and easy to swap for a maintained counter later.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import Project, User


def _dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for entry in path.rglob("*"):
        try:
            if entry.is_file():
                total += entry.stat().st_size
        except OSError:
            pass
    return total


def project_disk_bytes(project_id: int) -> int:
    """Bytes used by one project: its repo plus its cached diffs."""
    repo = settings.repos_dir / str(project_id)
    cache = settings.data_dir / "cache" / "diffs" / str(project_id)
    return _dir_size(repo) + _dir_size(cache)


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


def org_usage_bytes(db: Session, user: User) -> int:
    """Total on-disk bytes for the caller's organization."""
    return sum(project_disk_bytes(pid) for pid in org_project_ids(db, user))
