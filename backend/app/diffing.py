"""Serve diff artifacts with a lazy, content-addressed cache.

A diff is a pure function of two immutable commits, so results are cached by
the resolved (base sha, head sha) pair and never invalidated. The first request
for a pair computes and stores it; later requests just read the file. The
response carries an `X-Cache: HIT|MISS` header so callers can see what happened.
"""
from __future__ import annotations

from typing import Callable

from fastapi import HTTPException, Response, status

from vcs import ProjectRepo, ProjectRepoError

from . import diff_cache
from .storage import locked_repo, repo_for

# compute(repo, base_sha, head_sha) -> a Pydantic model with .model_dump_json()
Compute = Callable[[ProjectRepo, str, str], object]


def serve_diff(
    project_id: int, view: str, base: str, head: str, compute: Compute
) -> Response:
    # Resolving refs is a read-only git op, safe without the per-project lock.
    repo = repo_for(project_id)
    try:
        base_sha = repo.resolve_ref(base)
        head_sha = repo.resolve_ref(head)
    except ProjectRepoError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    cached = diff_cache.get(project_id, view, base_sha, head_sha)
    if cached is not None:
        return _json(cached, "HIT")

    # Only the (potentially slow) computation needs the lock. Re-check the cache
    # inside it so a concurrent request can't trigger a duplicate computation.
    with locked_repo(project_id) as locked:
        cached = diff_cache.get(project_id, view, base_sha, head_sha)
        if cached is not None:
            return _json(cached, "HIT")
        try:
            model = compute(locked, base_sha, head_sha)
        except ProjectRepoError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
        payload = model.model_dump_json()
        diff_cache.put(project_id, view, base_sha, head_sha, payload)
    return _json(payload, "MISS")


def _json(payload: str, cache_state: str) -> Response:
    return Response(
        content=payload,
        media_type="application/json",
        headers={"X-Cache": cache_state},
    )
