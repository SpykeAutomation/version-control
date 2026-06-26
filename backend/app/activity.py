"""Append-only project activity feed / audit log.

Each mutating endpoint calls `record(...)` to add one event. The row is added
to the *same* session as the action, so it commits (or rolls back) atomically
with it — the feed can never disagree with what actually happened. Reads are a
single indexed query on (project_id, created_at).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import Activity


def record(
    db: Session,
    *,
    project_id: int,
    actor_id: int | None,
    verb: str,
    target_type: str = "",
    target_id: str | int = "",
    summary: str = "",
) -> None:
    """Stage one activity event. The caller commits it with its own action."""
    db.add(
        Activity(
            project_id=project_id,
            actor_id=actor_id,
            verb=verb,
            target_type=target_type,
            target_id=str(target_id),
            summary=summary[:300],
        )
    )
