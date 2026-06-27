"""Pull requests, merging with conflict handling, and comments.

Covers: create a PR and merge branches, reporting conflicts instead of
failing (#5), and discussion comments from other users (#7).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from diff import ChangeSet, LadderDocument
from vcs import MergeConflict, ProjectRepoError

from ..auth import current_user
from ..db import get_db
from ..deps import require_member
from ..diffing import serve_diff
from ..models import Comment, PullRequest, User
from ..schemas import (
    CommentIn,
    CommentOut,
    MergeResult,
    PullIn,
    PullOut,
    UserOut,
)
from ..storage import locked_repo

router = APIRouter(prefix="/projects/{project_id}/pulls", tags=["pull requests"])


def _user_out(db: Session, user_id: int) -> UserOut:
    user = db.get(User, user_id)
    return UserOut.model_validate(user)


def _pull_out(db: Session, pr: PullRequest) -> PullOut:
    return PullOut(
        number=pr.number,
        title=pr.title,
        description=pr.description,
        source_branch=pr.source_branch,
        target_branch=pr.target_branch,
        status=pr.status,
        author=_user_out(db, pr.author_id),
        merge_sha=pr.merge_sha,
        created_at=pr.created_at,
    )


def _get_pull(db: Session, project_id: int, number: int) -> PullRequest:
    pr = db.scalar(
        select(PullRequest).where(
            PullRequest.project_id == project_id, PullRequest.number == number
        )
    )
    if pr is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pull request not found")
    return pr


@router.post("", response_model=PullOut, status_code=status.HTTP_201_CREATED)
def create_pull(
    project_id: int,
    payload: PullIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> PullOut:
    require_member(project_id, db, user)
    with locked_repo(project_id) as repo:
        for branch in (payload.source_branch, payload.target_branch):
            if not repo.branch_exists(branch):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, f"Unknown branch: {branch}"
                )

    next_number = (
        db.scalar(
            select(func.coalesce(func.max(PullRequest.number), 0)).where(
                PullRequest.project_id == project_id
            )
        )
        + 1
    )
    pr = PullRequest(
        project_id=project_id,
        number=next_number,
        title=payload.title,
        description=payload.description,
        source_branch=payload.source_branch,
        target_branch=payload.target_branch,
        author_id=user.id,
    )
    db.add(pr)
    db.commit()
    db.refresh(pr)
    return _pull_out(db, pr)


@router.get("", response_model=list[PullOut])
def list_pulls(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[PullOut]:
    require_member(project_id, db, user)
    pulls = db.scalars(
        select(PullRequest)
        .where(PullRequest.project_id == project_id)
        .order_by(PullRequest.number.desc())
    ).all()
    return [_pull_out(db, pr) for pr in pulls]


@router.get("/{number}", response_model=PullOut)
def get_pull(
    project_id: int,
    number: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> PullOut:
    require_member(project_id, db, user)
    return _pull_out(db, _get_pull(db, project_id, number))


@router.get("/{number}/diff", response_model=ChangeSet)
def pull_diff(
    project_id: int,
    number: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """What this PR would change (target -> source), cached by commit pair."""
    require_member(project_id, db, user)
    pr = _get_pull(db, project_id, number)
    return serve_diff(
        project_id,
        "changeset",
        pr.target_branch,
        pr.source_branch,
        lambda r, b, h: r.diff_refs(b, h),
    )


@router.get("/{number}/diff/ladder", response_model=LadderDocument)
def pull_ladder_diff(
    project_id: int,
    number: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Drawable ladder-diagram diff for the PR (target -> source)."""
    require_member(project_id, db, user)
    pr = _get_pull(db, project_id, number)
    return serve_diff(
        project_id,
        "ladder",
        pr.target_branch,
        pr.source_branch,
        lambda r, b, h: r.ladder_diff_refs(
            b, h, old_label=pr.target_branch, new_label=pr.source_branch
        ),
    )


@router.post("/{number}/merge", response_model=MergeResult)
def merge_pull(
    project_id: int,
    number: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> MergeResult:
    require_member(project_id, db, user)
    pr = _get_pull(db, project_id, number)
    if pr.status != "open":
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Pull request is already {pr.status}"
        )
    try:
        with locked_repo(project_id) as repo:
            merge_sha = repo.merge(
                pr.source_branch,
                pr.target_branch,
                message=f"Merge pull request #{pr.number}: {pr.title}",
                author=(user.name, user.email),
            )
    except MergeConflict as exc:
        # Pilot behaviour: report the conflict, leave the PR open to resolve.
        return MergeResult(status="conflict", message=str(exc), conflicts=exc.files)
    except ProjectRepoError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    pr.status = "merged"
    pr.merge_sha = merge_sha
    db.commit()
    return MergeResult(
        status="merged", message="Merged successfully", merge_sha=merge_sha
    )


@router.get("/{number}/comments", response_model=list[CommentOut])
def list_comments(
    project_id: int,
    number: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[CommentOut]:
    require_member(project_id, db, user)
    pr = _get_pull(db, project_id, number)
    comments = db.scalars(
        select(Comment)
        .where(Comment.pull_request_id == pr.id)
        .order_by(Comment.created_at.asc())
    ).all()
    return [
        CommentOut(
            id=c.id,
            author=_user_out(db, c.author_id),
            body=c.body,
            created_at=c.created_at,
        )
        for c in comments
    ]


@router.post(
    "/{number}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED
)
def add_comment(
    project_id: int,
    number: int,
    payload: CommentIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> CommentOut:
    require_member(project_id, db, user)
    pr = _get_pull(db, project_id, number)
    comment = Comment(pull_request_id=pr.id, author_id=user.id, body=payload.body)
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return CommentOut(
        id=comment.id,
        author=_user_out(db, user.id),
        body=comment.body,
        created_at=comment.created_at,
    )
