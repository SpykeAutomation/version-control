"""Per-organization storage usage."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import usage
from ..auth import current_user
from ..db import get_db
from ..models import User
from ..schemas import StorageUsage

router = APIRouter(prefix="/storage", tags=["storage"])


@router.get("", response_model=StorageUsage)
def storage_usage(
    db: Session = Depends(get_db), user: User = Depends(current_user)
) -> StorageUsage:
    """How much of the organization's quota the caller's org is using (logical
    bytes of committed uploads, read from the maintained counter)."""
    return StorageUsage(
        used_bytes=usage.bucket_used_bytes(db, user),
        limit_bytes=usage.bucket_limit_bytes(db, user),
        project_count=len(usage.org_project_ids(db, user)),
    )
