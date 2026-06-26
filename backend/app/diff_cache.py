"""On-disk cache for computed diff artifacts.

A diff is a pure function of two immutable Git commits, so a cached result can
never go stale. Entries are keyed by (project, view, base sha, head sha, file
path) and stored as JSON under the data dir. The schema version is folded into
the file name; bumping it for a view transparently invalidates old entries
(their key no longer matches) without any explicit purge.

Most views are per-file (a single L5X file or a single non-L5X blob), so the
file path is part of the key; the project-wide manifest uses an empty path.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Optional

from diff.ladder_models import SCHEMA_VERSION as LADDER_SCHEMA

from .config import settings

# Output-format version per view. Bump when a view's JSON shape changes.
SCHEMA_VERSION = {
    "manifest": 1,
    "changeset": 1,
    "ladder": LADDER_SCHEMA,
    "text": 1,
    "compare": 1,
}


def _path(
    project_id: int, view: str, base_sha: str, head_sha: str, file_path: str = ""
) -> Path:
    schema = SCHEMA_VERSION[view]
    root = settings.data_dir / "cache" / "diffs" / str(project_id)
    # The file path can contain slashes and arbitrary characters, so fold a
    # short stable hash of it into the name rather than using it directly.
    tag = hashlib.sha1(file_path.encode("utf-8")).hexdigest()[:12]
    return root / f"{view}-v{schema}-{base_sha}-{head_sha}-{tag}.json"


def get(
    project_id: int, view: str, base_sha: str, head_sha: str, file_path: str = ""
) -> Optional[str]:
    """Return the cached JSON payload for this diff, or None on a miss."""
    try:
        return _path(project_id, view, base_sha, head_sha, file_path).read_text(
            encoding="utf-8"
        )
    except FileNotFoundError:
        return None


def put(
    project_id: int,
    view: str,
    base_sha: str,
    head_sha: str,
    payload: str,
    file_path: str = "",
) -> None:
    """Store a diff payload atomically (temp file + rename)."""
    path = _path(project_id, view, base_sha, head_sha, file_path)
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
    _evict_if_over_cap()


def _evict_if_over_cap() -> None:
    """Keep the whole diff cache under the configured size cap (LRU by mtime).

    A diff is a pure function of its commits, so eviction is always safe — a
    later request simply recomputes and re-stores it. Best-effort: errors while
    measuring or deleting are ignored, which is fine under concurrent writers
    since the worst case is a redundant recompute."""
    cap = settings.diff_cache_max_bytes
    root = settings.data_dir / "cache" / "diffs"
    if cap <= 0 or not root.exists():
        return
    entries: list[tuple[float, int, Path]] = []
    total = 0
    for cached in root.rglob("*.json"):
        try:
            stat = cached.stat()
        except OSError:
            continue
        entries.append((stat.st_mtime, stat.st_size, cached))
        total += stat.st_size
    if total <= cap:
        return
    entries.sort(key=lambda e: e[0])  # oldest first
    for _mtime, size, cached in entries:
        if total <= cap:
            break
        try:
            cached.unlink()
            total -= size
        except OSError:
            pass


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
