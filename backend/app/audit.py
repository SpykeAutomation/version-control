"""Account- and security-level audit trail (app.models.AuditLog).

The sibling of app.activity: that records *per-project* events; this records
account-level ones — CLI logins and revocations, member removals, account
deletions — which aren't tied to a single project. Like activity.record, this
only stages the row (db.add); the caller commits it alongside its own action.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import AuditLog


def record(
    db: Session,
    *,
    action: str,
    actor_id: int | None,
    target_user_id: int | None = None,
    target_type: str = "",
    target_id: str | int = "",
    summary: str = "",
    ip: str | None = None,
) -> None:
    """Stage one audit event. The caller commits it with its own action."""
    db.add(
        AuditLog(
            action=action,
            actor_id=actor_id,
            target_user_id=target_user_id,
            target_type=target_type,
            target_id=str(target_id),
            summary=summary[:300],
            ip=ip,
        )
    )
