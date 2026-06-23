"""Map a project id to its on-disk Git repo, with per-project locking.

All Git operations for one project share a working tree, so they must not run
concurrently (one request checking out a branch while another commits would
corrupt state). A process-wide lock per project id serializes them. This is
why the pilot runs a single web worker; scaling out later means moving these
locks to the database or a bare-repo-per-operation model.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from contextlib import contextmanager
from collections.abc import Iterator

from vcs import ProjectRepo

from .config import settings

_locks: dict[int, threading.Lock] = defaultdict(threading.Lock)


def repo_for(project_id: int) -> ProjectRepo:
    return ProjectRepo(settings.repos_dir / str(project_id))


@contextmanager
def locked_repo(project_id: int) -> Iterator[ProjectRepo]:
    with _locks[project_id]:
        yield repo_for(project_id)
