"""Per-organization storage usage."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import usage
from ..auth import current_user
from ..config import settings
from ..db import get_db
from ..models import User
from ..schemas import StorageUsage

router = APIRouter(prefix="/storage", tags=["storage"])


@router.get("", response_model=StorageUsage)
def storage_usage(
    db: Session = Depends(get_db), user: User = Depends(current_user)
) -> StorageUsage:
    """How much of the organization's quota the caller's org is using (repos +
    cached diffs)."""
    ids = usage.org_project_ids(db, user)
    used = sum(usage.project_disk_bytes(pid) for pid in ids)
    return StorageUsage(
        used_bytes=used,
        limit_bytes=settings.org_storage_limit_bytes,
        project_count=len(ids),
    )
