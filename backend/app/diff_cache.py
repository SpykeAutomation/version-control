"""On-disk cache for computed diff artifacts.

A diff is a pure function of two immutable Git commits, so a cached result can
never go stale. Entries are keyed by (project, view, base sha, head sha) and
stored as JSON under the data dir. The schema version is folded into the file
name; bumping it for a view transparently invalidates old entries (their key
no longer matches) without any explicit purge.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

from diff.ladder_models import SCHEMA_VERSION as LADDER_SCHEMA

from .config import settings
from .tree import SCHEMA_VERSION as TREE_SCHEMA

# Output-format version per view. Bump when a view's JSON shape changes.
SCHEMA_VERSION = {
    "changeset": 1,
    "ladder": LADDER_SCHEMA,
    # Single-commit ladder diffs share the ladder shape but carry different
    # version labels (short shas, not ref names), so they need their own
    # namespace to avoid colliding with the generic ref-to-ref ladder view.
    "commit-ladder": LADDER_SCHEMA,
    # The project-organizer tree at a commit (full structure + change status).
    "tree": TREE_SCHEMA,
}


def _path(project_id: int, view: str, base_sha: str, head_sha: str) -> Path:
    schema = SCHEMA_VERSION[view]
    root = settings.data_dir / "cache" / "diffs" / str(project_id)
    return root / f"{view}-v{schema}-{base_sha}-{head_sha}.json"


def get(project_id: int, view: str, base_sha: str, head_sha: str) -> Optional[str]:
    """Return the cached JSON payload for this diff, or None on a miss."""
    try:
        return _path(project_id, view, base_sha, head_sha).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def put(project_id: int, view: str, base_sha: str, head_sha: str, payload: str) -> None:
    """Store a diff payload atomically (temp file + rename)."""
    path = _path(project_id, view, base_sha, head_sha)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def clear_project(project_id: int) -> None:
    """Drop every cached diff for a project (e.g. when the project is deleted).

    Note: because keys are immutable commit pairs, entries are otherwise safe
    to keep. A periodic reachability-based sweep (dropping entries whose commits
    are no longer reachable after a branch delete) can replace this later.
    """
    root = settings.data_dir / "cache" / "diffs" / str(project_id)
    if root.exists():
        for cached in root.glob("*.json"):
            cached.unlink(missing_ok=True)
