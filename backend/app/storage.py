"""Map a project id to its on-disk Git repo, with per-project locking.

All *mutating* Git operations for one project share a working tree, so they
must not run concurrently (one request checking out a branch while another
commits would corrupt state). A per-project **file lock** (flock) serializes
them across every process on this host — so these locks no longer force a
single web worker — and the OS releases a crashed holder's lock automatically.
Lock files live under repos_dir/.locks and are never deleted: unlinking a file
another process may already hold open would silently split the lock in two.

Read-only operations on committed history (diffs between two SHAs, log, branch
and tag listings) use plain `repo_for` with no lock: they read immutable
objects and atomically-updated refs via git plumbing — semantic diffs
materialize snapshots into their own ephemeral worktree — so a concurrent
commit cannot corrupt them, and a slow diff never blocks an upload.

Scaling to multiple *machines* still needs shared repo storage and a
distributed lock; flock covers many workers on one host.
"""
from __future__ import annotations

import fcntl
import shutil
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path

from vcs import ProjectRepo

from .config import settings


def repo_for(project_id: int) -> ProjectRepo:
    return ProjectRepo(settings.repos_dir / str(project_id))


def _lock_path(project_id: int) -> Path:
    locks = settings.repos_dir / ".locks"
    locks.mkdir(parents=True, exist_ok=True)
    return locks / f"{project_id}.lock"


@contextmanager
def locked_repo(project_id: int) -> Iterator[ProjectRepo]:
    """Exclusive per-project lock for operations that touch the working tree
    or write refs. Blocks until the current holder finishes; released on exit
    (or by the OS if the holder dies)."""
    with open(_lock_path(project_id), "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield repo_for(project_id)
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def delete_repo(project_id: int) -> None:
    """Remove a project's working repo from disk, under the project lock so a
    concurrent operation can't be mid-checkout while the tree is removed. The
    lock file itself stays behind (see module docstring)."""
    with locked_repo(project_id):
        shutil.rmtree(settings.repos_dir / str(project_id), ignore_errors=True)
