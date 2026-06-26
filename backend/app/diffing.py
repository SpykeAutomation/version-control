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
from .schemas import (
    ChangedFile,
    CompareRow,
    CompareSummary,
    CompareView,
    DiffManifest,
    TextDiff,
)
from .storage import locked_repo, repo_for

# compute(repo, base_sha, head_sha) -> a Pydantic model with .model_dump_json()
Compute = Callable[[ProjectRepo, str, str], object]

# Per-changed-file drill-down views the frontend can request from a manifest.
VIEWS_FOR_KIND = {"l5x": ["changeset", "ladder"], "file": ["text"]}


def serve_diff(
    project_id: int,
    view: str,
    base: str,
    head: str,
    compute: Compute,
    *,
    file_path: str = "",
) -> Response:
    """Serve a cached diff artifact. `file_path` scopes per-file views (a single
    L5X file or a non-L5X blob) and forms part of the cache key; the project-wide
    manifest leaves it empty."""
    # Resolving refs is a read-only git op, safe without the per-project lock.
    repo = repo_for(project_id)
    try:
        base_sha = repo.resolve_ref(base)
        head_sha = repo.resolve_ref(head)
    except ProjectRepoError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    cached = diff_cache.get(project_id, view, base_sha, head_sha, file_path)
    if cached is not None:
        return _json(cached, "HIT")

    # Only the (potentially slow) computation needs the lock. Re-check the cache
    # inside it so a concurrent request can't trigger a duplicate computation.
    with locked_repo(project_id) as locked:
        cached = diff_cache.get(project_id, view, base_sha, head_sha, file_path)
        if cached is not None:
            return _json(cached, "HIT")
        try:
            model = compute(locked, base_sha, head_sha)
        except ProjectRepoError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
        payload = model.model_dump_json()
        diff_cache.put(project_id, view, base_sha, head_sha, payload, file_path)
    return _json(payload, "MISS")


def _json(payload: str, cache_state: str) -> Response:
    return Response(
        content=payload,
        media_type="application/json",
        headers={"X-Cache": cache_state},
    )


# --- shared helpers for the (project and pull-request) diff endpoints ---


def l5x_name(path: str) -> str:
    """Extract an L5X file name from a manifest path like 'l5x/<name>'."""
    p = path.strip().strip("/")
    if p.startswith("l5x/"):
        p = p[len("l5x/") :]
    p = p.strip("/")
    if not p or "/" in p:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"invalid L5X path: {path!r}")
    return p


def files_path(path: str) -> str:
    """Validate a client-supplied non-L5X path stays under files/ (no traversal)."""
    p = path.strip().lstrip("/")
    if not p.startswith("files/") or ".." in p.split("/"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"invalid file path: {path!r}")
    return p


def build_manifest(repo: ProjectRepo, base_sha: str, head_sha: str) -> DiffManifest:
    """The list of changed files between two refs, with their drill-down views."""
    return DiffManifest(
        files=[
            ChangedFile(
                path=f.path,
                kind=f.kind,
                change=f.change,
                views=VIEWS_FOR_KIND.get(f.kind, []),
            )
            for f in repo.changed_files(base_sha, head_sha)
        ]
    )


def build_text_diff(
    repo: ProjectRepo, base_sha: str, head_sha: str, repo_path: str
) -> TextDiff:
    """Unified line diff (or binary marker) for one non-L5X file."""
    binary, unified = repo.text_file_diff(base_sha, head_sha, repo_path)
    return TextDiff(path=repo_path, binary=binary, unified=unified)


class _Impact:
    """Mutable tally for one or many L5X ChangeSets."""

    def __init__(self) -> None:
        self.rungs_added = self.rungs_removed = self.rungs_modified = 0
        self.routines = self.tags = 0
        self.symbols: list[str] = []


def _changeset_impact(changeset) -> _Impact:
    """Roll one L5X file's ChangeSet up into rung/routine/tag counts and the
    names of every affected symbol (tags, UDTs, AOIs, modules, routines)."""
    imp = _Impact()
    imp.tags += len(changeset.controller_tags)
    imp.symbols += [e.name for e in changeset.controller_tags]
    imp.symbols += [e.name for e in changeset.data_types]
    imp.symbols += [e.name for e in changeset.add_on_instructions]
    imp.symbols += [e.name for e in changeset.modules]
    for program in changeset.programs:
        imp.tags += len(program.tags)
        imp.symbols += [t.name for t in program.tags]
        for routine in program.routines:
            imp.routines += 1
            imp.symbols.append(f"{program.name}/{routine.name}")
            for rung in routine.rungs:
                if rung.kind == "added":
                    imp.rungs_added += 1
                elif rung.kind == "removed":
                    imp.rungs_removed += 1
                else:  # modified | comment_changed
                    imp.rungs_modified += 1
    return imp


def build_compare(repo: ProjectRepo, base_sha: str, head_sha: str) -> CompareView:
    """The Compare view model for two refs: per-file impact rows plus rolled-up
    summary counts (rungs, routines, tags, commits) and the affected symbols.

    A pure function of the two commits, so it caches like any other diff."""
    summary = CompareSummary(commits=repo.commit_count(base_sha, head_sha))
    rows: list[CompareRow] = []
    affected: list[str] = []
    for changed in repo.changed_files(base_sha, head_sha):
        summary.files_changed += 1
        row = CompareRow(
            path=changed.path,
            kind=changed.kind,
            change=changed.change,
            views=VIEWS_FOR_KIND.get(changed.kind, []),
        )
        if changed.kind == "l5x":
            summary.l5x_changed += 1
            name = changed.path[len("l5x/"):]
            try:
                changeset = repo.diff_refs(base_sha, head_sha, name)
            except ProjectRepoError:
                changeset = None
            if changeset is not None:
                imp = _changeset_impact(changeset)
                row.rungs_added = imp.rungs_added
                row.rungs_removed = imp.rungs_removed
                row.rungs_modified = imp.rungs_modified
                row.symbols = imp.symbols
                summary.rungs_added += imp.rungs_added
                summary.rungs_removed += imp.rungs_removed
                summary.rungs_modified += imp.rungs_modified
                summary.routines_modified += imp.routines
                summary.tags_impacted += imp.tags
                affected += imp.symbols
        rows.append(row)
    seen: dict[str, None] = {}
    for sym in affected:
        seen.setdefault(sym, None)
    return CompareView(
        base=base_sha, head=head_sha, summary=summary,
        files=rows, affected_symbols=list(seen),
    )
