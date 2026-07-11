"""Shared plumbing for the two comment scopes.

PR discussions and commit-page discussions live in one `comments` table (one
scope per row — see the model's check constraint) and behave identically:
flat creation-order listing with `X-Total-Count`, replies at any depth whose
parent must belong to the same discussion, author-only body edits, and
author-or-manager deletes that cascade to the reply subtree. The routers only
differ in how they resolve their scope (a PR row / a resolved commit sha) and
what activity entry they write, so everything else lives here.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .deps import MANAGER_ROLES, membership_role
from .models import Comment, User
from .schemas import CommentAnchor, CommentIn, CommentOut, CommentUpdate, UserOut
from .serialize import user_out, users_out

# A scope is the WHERE clauses that pin one discussion, e.g.
# [Comment.pull_request_id == pr.id] or
# [Comment.project_id == pid, Comment.commit_sha == sha].
Scope = list


def is_manager(db: Session, project_id: int, user: User) -> bool:
    """Owner or admin on this project (may delete any comment / open PR)."""
    return membership_role(project_id, db, user) in MANAGER_ROLES


def anchor_out(c: Comment) -> CommentAnchor | None:
    if not any((c.anchor_path, c.anchor_routine, c.anchor_rung, c.anchor_sha)):
        return None
    return CommentAnchor(
        path=c.anchor_path, routine=c.anchor_routine,
        rung=c.anchor_rung, sha=c.anchor_sha,
    )


def comment_out(db: Session, c: Comment, author: UserOut | None = None) -> CommentOut:
    return CommentOut(
        id=c.id,
        author=author or user_out(db, db.get(User, c.author_id)),
        body=c.body,
        resolved=c.resolved,
        parent_id=c.parent_id,
        anchor=anchor_out(c),
        created_at=c.created_at,
        edited_at=c.edited_at,
    )


def list_comments(
    db: Session, response: Response, scope: Scope, *, limit: int, offset: int
) -> list[CommentOut]:
    """One discussion's comments in creation order, flat (the frontend nests
    by `parent_id`). Authors are batch-loaded — no per-comment query — and the
    set is paginated via `limit`/`offset` (`X-Total-Count` header)."""
    limit = max(1, min(limit, 500))
    total = db.scalar(select(func.count()).select_from(Comment).where(*scope))
    comments = db.scalars(
        select(Comment)
        .where(*scope)
        .order_by(Comment.created_at.asc(), Comment.id.asc())
        .limit(limit)
        .offset(max(0, offset))
    ).all()
    umap = users_out(db, [c.author_id for c in comments])
    response.headers["X-Total-Count"] = str(total or 0)
    return [comment_out(db, c, umap.get(c.author_id)) for c in comments]


def create_comment(
    db: Session,
    user: User,
    payload: CommentIn,
    scope: Scope,
    scope_label: str,
    **scope_fields,
) -> Comment:
    """Add a comment (top-level, a reply, or change-anchored) to one discussion.

    A reply's parent must belong to the same discussion; the depth is
    unlimited — the true parent chain is stored so the frontend can render one
    visual level with quote-links on reply-to-a-reply. The caller commits (so
    it can record activity in the same transaction)."""
    if payload.parent_id is not None:
        parent = db.scalar(
            select(Comment).where(Comment.id == payload.parent_id, *scope)
        )
        if parent is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Parent comment not found on this {scope_label}",
            )
    anchor = payload.anchor or CommentAnchor()
    comment = Comment(
        author_id=user.id,
        parent_id=payload.parent_id,
        body=payload.body,
        anchor_path=anchor.path,
        anchor_routine=anchor.routine,
        anchor_rung=anchor.rung,
        anchor_sha=anchor.sha,
        **scope_fields,
    )
    db.add(comment)
    return comment


def get_comment(db: Session, comment_id: int, scope: Scope) -> Comment:
    """The comment with this id inside one discussion, or 404."""
    comment = db.scalar(select(Comment).where(Comment.id == comment_id, *scope))
    if comment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comment not found")
    return comment


def apply_update(comment: Comment, payload: CommentUpdate, user: User) -> None:
    """Edit the body (author only) and/or set resolved (any member)."""
    if payload.body is not None:
        if comment.author_id != user.id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Only the author can edit a comment"
            )
        comment.body = payload.body
        comment.edited_at = datetime.now(timezone.utc)
    if payload.resolved is not None:
        comment.resolved = payload.resolved


def ensure_can_delete(
    db: Session, project_id: int, user: User, comment: Comment
) -> None:
    if comment.author_id != user.id and not is_manager(db, project_id, user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only the author or a manager can delete this comment",
        )
