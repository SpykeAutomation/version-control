"""Pull requests: review/approval workflow, merging with conflict handling,
and threaded, change-anchored comments.

Merging into a protected branch can require a number of approvals (set on the
branch's protection). The frontend greys the merge button from `can_merge`, and
the backend independently re-checks the gate on merge — UI gating is not
security.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from diff import ChangeSet, LadderDocument
from vcs import MergeConflict, ProjectRepoError

from .. import activity
from ..auth import current_user
from ..db import get_db
from ..deps import MANAGER_ROLES, membership_role, require_member
from ..diffing import (
    build_manifest,
    build_text_diff,
    files_path,
    l5x_name,
    serve_diff,
)
from ..models import (
    BranchProtection,
    Comment,
    ProjectMember,
    PullApproval,
    PullRequest,
    PullReviewer,
    User,
)
from ..schemas import (
    CommentIn,
    CommentOut,
    CommentUpdate,
    CommentAnchor,
    DiffManifest,
    MergeabilityOut,
    MergeResult,
    PullIn,
    PullOut,
    PullUpdate,
    ReviewerIn,
    ReviewOut,
    TextDiff,
    UserOut,
)
from ..serialize import user_out, users_out
from ..storage import locked_repo, repo_for

router = APIRouter(prefix="/projects/{project_id}/pulls", tags=["pull requests"])


# --- helpers ----------------------------------------------------------------
def _get_pull(db: Session, project_id: int, number: int) -> PullRequest:
    pr = db.scalar(
        select(PullRequest).where(
            PullRequest.project_id == project_id, PullRequest.number == number
        )
    )
    if pr is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pull request not found")
    return pr


def _required_approvals(db: Session, project_id: int, branch: str) -> int:
    """Approvals a PR into `branch` needs, from the branch's protection (0 if
    the branch isn't protected or has no requirement)."""
    row = db.scalar(
        select(BranchProtection).where(
            BranchProtection.project_id == project_id,
            BranchProtection.branch == branch,
        )
    )
    return row.required_approvals if row else 0


def _is_manager(db: Session, project_id: int, user: User) -> bool:
    return membership_role(project_id, db, user) in MANAGER_ROLES


def _pulls_out(db: Session, prs: list[PullRequest]) -> list[PullOut]:
    """Serialize many PRs with their reviewers, reviews, and approval gate — in a
    fixed number of queries (no per-PR N+1)."""
    if not prs:
        return []
    project_id = prs[0].project_id
    pr_ids = [pr.id for pr in prs]

    required_by_branch: dict[str, int] = {
        row.branch: row.required_approvals
        for row in db.scalars(
            select(BranchProtection).where(
                BranchProtection.project_id == project_id
            )
        ).all()
    }
    reviewers_by_pr: dict[int, list[int]] = {pid: [] for pid in pr_ids}
    for pid, uid in db.execute(
        select(PullReviewer.pull_request_id, PullReviewer.user_id).where(
            PullReviewer.pull_request_id.in_(pr_ids)
        )
    ).all():
        reviewers_by_pr[pid].append(uid)
    reviews_by_pr: dict[int, list[PullApproval]] = {pid: [] for pid in pr_ids}
    for review in db.scalars(
        select(PullApproval).where(PullApproval.pull_request_id.in_(pr_ids))
    ).all():
        reviews_by_pr[review.pull_request_id].append(review)

    ids = {pr.author_id for pr in prs}
    for lst in reviewers_by_pr.values():
        ids.update(lst)
    for reviews in reviews_by_pr.values():
        ids.update(r.user_id for r in reviews)
    umap = users_out(db, list(ids))

    out: list[PullOut] = []
    for pr in prs:
        reviews = reviews_by_pr[pr.id]
        approvals = sum(1 for r in reviews if r.state == "approved")
        required = required_by_branch.get(pr.target_branch, 0)
        out.append(
            PullOut(
                number=pr.number,
                title=pr.title,
                description=pr.description,
                source_branch=pr.source_branch,
                target_branch=pr.target_branch,
                status=pr.status,
                author=umap.get(pr.author_id) or user_out(db, db.get(User, pr.author_id)),
                merge_sha=pr.merge_sha,
                created_at=pr.created_at,
                updated_at=pr.updated_at,
                reviewers=[umap[uid] for uid in reviewers_by_pr[pr.id] if uid in umap],
                reviews=[
                    ReviewOut(user=umap[r.user_id], state=r.state, created_at=r.created_at)
                    for r in reviews
                    if r.user_id in umap
                ],
                required_approvals=required,
                approvals=approvals,
                approved=approvals >= required,
            )
        )
    return out


def _pull_out(db: Session, pr: PullRequest) -> PullOut:
    return _pulls_out(db, [pr])[0]


# --- pull requests ----------------------------------------------------------
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
    activity.record(
        db, project_id=project_id, actor_id=user.id, verb="pull.opened",
        target_type="pull", target_id=next_number,
        summary=f"opened #{next_number}: {payload.title}",
    )
    db.commit()
    db.refresh(pr)
    return _pull_out(db, pr)


@router.get("", response_model=list[PullOut])
def list_pulls(
    project_id: int,
    response: Response,
    status_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[PullOut]:
    """Pull requests, newest first. Optional `status_filter` (open|merged|closed);
    paginated via `limit`/`offset`, with the total in `X-Total-Count`."""
    require_member(project_id, db, user)
    limit = max(1, min(limit, 200))
    where = [PullRequest.project_id == project_id]
    if status_filter:
        where.append(PullRequest.status == status_filter)
    total = db.scalar(select(func.count()).select_from(PullRequest).where(*where))
    pulls = db.scalars(
        select(PullRequest)
        .where(*where)
        .order_by(PullRequest.number.desc())
        .limit(limit)
        .offset(max(0, offset))
    ).all()
    response.headers["X-Total-Count"] = str(total or 0)
    return _pulls_out(db, list(pulls))


@router.get("/{number}", response_model=PullOut)
def get_pull(
    project_id: int,
    number: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> PullOut:
    require_member(project_id, db, user)
    return _pull_out(db, _get_pull(db, project_id, number))


@router.patch("/{number}", response_model=PullOut)
def update_pull(
    project_id: int,
    number: int,
    payload: PullUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> PullOut:
    """Edit a PR's title/description (any project member). The branches can't be
    changed — open a new PR for a different comparison."""
    require_member(project_id, db, user)
    pr = _get_pull(db, project_id, number)
    if payload.title is not None:
        pr.title = payload.title
    if payload.description is not None:
        pr.description = payload.description
    db.commit()
    db.refresh(pr)
    return _pull_out(db, pr)


@router.delete("/{number}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pull(
    project_id: int,
    number: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Delete (abandon) an *open* PR — the author or a manager. A merged PR is
    history and is never deleted; to undo direction, delete and recreate."""
    require_member(project_id, db, user)
    pr = _get_pull(db, project_id, number)
    if pr.status != "open":
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Cannot delete a {pr.status} pull request"
        )
    if pr.author_id != user.id and not _is_manager(db, project_id, user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the author or a manager can delete this PR"
        )
    db.delete(pr)  # cascades to its reviewers, approvals, and comments
    activity.record(
        db, project_id=project_id, actor_id=user.id, verb="pull.deleted",
        target_type="pull", target_id=number, summary=f"deleted #{number}",
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- reviewers & approvals --------------------------------------------------
@router.post("/{number}/reviewers", response_model=PullOut, status_code=201)
def add_reviewer(
    project_id: int,
    number: int,
    payload: ReviewerIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> PullOut:
    """Invite a project member to review/approve a PR (the author or a manager)."""
    require_member(project_id, db, user)
    pr = _get_pull(db, project_id, number)
    if pr.author_id != user.id and not _is_manager(db, project_id, user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the author or a manager can add reviewers"
        )
    invitee = db.scalar(select(User).where(User.email == payload.email))
    if invitee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No user with that email")
    if membership_role(project_id, db, invitee) is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Reviewer must be a member of this project"
        )
    existing = db.scalar(
        select(PullReviewer).where(
            PullReviewer.pull_request_id == pr.id,
            PullReviewer.user_id == invitee.id,
        )
    )
    if existing is None:
        db.add(PullReviewer(pull_request_id=pr.id, user_id=invitee.id))
        db.commit()
    return _pull_out(db, pr)


@router.delete(
    "/{number}/reviewers/{user_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_reviewer(
    project_id: int,
    number: int,
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Uninvite a reviewer (the author or a manager)."""
    require_member(project_id, db, user)
    pr = _get_pull(db, project_id, number)
    if pr.author_id != user.id and not _is_manager(db, project_id, user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the author or a manager can remove reviewers"
        )
    row = db.scalar(
        select(PullReviewer).where(
            PullReviewer.pull_request_id == pr.id, PullReviewer.user_id == user_id
        )
    )
    if row is not None:
        db.delete(row)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _set_review(
    db: Session, project_id: int, number: int, user: User, state: str
) -> PullOut:
    require_member(project_id, db, user)
    pr = _get_pull(db, project_id, number)
    if pr.status != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Pull request is {pr.status}")
    existing = db.scalar(
        select(PullApproval).where(
            PullApproval.pull_request_id == pr.id, PullApproval.user_id == user.id
        )
    )
    if existing is None:
        db.add(PullApproval(pull_request_id=pr.id, user_id=user.id, state=state))
    else:
        existing.state = state
    activity.record(
        db, project_id=project_id, actor_id=user.id, verb=f"pull.{state}",
        target_type="pull", target_id=number,
        summary=f"{state.replace('_', ' ')} on #{number}",
    )
    db.commit()
    db.refresh(pr)
    return _pull_out(db, pr)


@router.post("/{number}/approve", response_model=PullOut)
def approve_pull(
    project_id: int,
    number: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> PullOut:
    """Record your approval (any member). Re-approving just updates your verdict."""
    return _set_review(db, project_id, number, user, "approved")


@router.post("/{number}/request-changes", response_model=PullOut)
def request_changes(
    project_id: int,
    number: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> PullOut:
    """Record a changes-requested verdict (any member)."""
    return _set_review(db, project_id, number, user, "changes_requested")


@router.delete("/{number}/review", status_code=status.HTTP_204_NO_CONTENT)
def dismiss_own_review(
    project_id: int,
    number: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Withdraw your own approval/changes-requested verdict."""
    require_member(project_id, db, user)
    pr = _get_pull(db, project_id, number)
    row = db.scalar(
        select(PullApproval).where(
            PullApproval.pull_request_id == pr.id, PullApproval.user_id == user.id
        )
    )
    if row is not None:
        db.delete(row)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{number}/mergeability", response_model=MergeabilityOut)
def pull_mergeability(
    project_id: int,
    number: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> MergeabilityOut:
    """Whether this PR can merge right now: a lock-free conflict dry-run plus the
    approval gate. The frontend uses `can_merge` to enable the merge button."""
    require_member(project_id, db, user)
    pr = _get_pull(db, project_id, number)
    try:
        mergeable, conflicts = repo_for(project_id).merge_preview(
            pr.target_branch, pr.source_branch
        )
    except ProjectRepoError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    required = _required_approvals(db, project_id, pr.target_branch)
    approvals = db.scalar(
        select(func.count()).select_from(PullApproval).where(
            PullApproval.pull_request_id == pr.id, PullApproval.state == "approved"
        )
    ) or 0
    approved = approvals >= required
    return MergeabilityOut(
        mergeable=mergeable,
        conflicts=conflicts,
        approvals=approvals,
        required_approvals=required,
        approved=approved,
        can_merge=pr.status == "open" and mergeable and approved,
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
    # Approval gate: re-checked here regardless of any frontend gating.
    required = _required_approvals(db, project_id, pr.target_branch)
    if required:
        approvals = db.scalar(
            select(func.count()).select_from(PullApproval).where(
                PullApproval.pull_request_id == pr.id,
                PullApproval.state == "approved",
            )
        ) or 0
        if approvals < required:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Needs {required} approval(s) to merge into "
                f"'{pr.target_branch}' (has {approvals})",
            )
    try:
        with locked_repo(project_id) as repo:
            merge_sha = repo.merge(
                pr.source_branch,
                pr.target_branch,
                message=f"Merge pull request #{pr.number}: {pr.title}",
                author_name=f"{user.first_name} {user.last_name}".strip(),
                author_email=user.email,
            )
    except MergeConflict as exc:
        # Pilot behaviour: report the conflict, leave the PR open to resolve.
        return MergeResult(status="conflict", message=str(exc), conflicts=exc.files)
    except ProjectRepoError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    pr.status = "merged"
    pr.merge_sha = merge_sha
    activity.record(
        db, project_id=project_id, actor_id=user.id, verb="pull.merged",
        target_type="pull", target_id=number,
        summary=f"merged #{number} ({pr.source_branch} → {pr.target_branch})",
    )
    db.commit()
    return MergeResult(
        status="merged", message="Merged successfully", merge_sha=merge_sha
    )


# --- diffs (PR is target -> source) -----------------------------------------
@router.get("/{number}/diff", response_model=DiffManifest)
def pull_diff(
    project_id: int,
    number: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Files this PR would change (target -> source); drill in per file below."""
    require_member(project_id, db, user)
    pr = _get_pull(db, project_id, number)
    return serve_diff(
        project_id, "manifest", pr.target_branch, pr.source_branch, build_manifest
    )


@router.get("/{number}/diff/changeset", response_model=ChangeSet)
def pull_changeset(
    project_id: int,
    number: int,
    path: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Semantic diff of one L5X file in the PR (target -> source)."""
    require_member(project_id, db, user)
    pr = _get_pull(db, project_id, number)
    name = l5x_name(path)
    return serve_diff(
        project_id,
        "changeset",
        pr.target_branch,
        pr.source_branch,
        lambda r, b, h: r.diff_refs(b, h, name),
        file_path=f"l5x/{name}",
    )


@router.get("/{number}/diff/ladder", response_model=LadderDocument)
def pull_ladder_diff(
    project_id: int,
    number: int,
    path: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Drawable ladder-diagram diff of one L5X file in the PR (target -> source)."""
    require_member(project_id, db, user)
    pr = _get_pull(db, project_id, number)
    name = l5x_name(path)
    return serve_diff(
        project_id,
        "ladder",
        pr.target_branch,
        pr.source_branch,
        lambda r, b, h: r.ladder_diff_refs(
            b, h, name, old_label=pr.target_branch, new_label=pr.source_branch
        ),
        file_path=f"l5x/{name}",
    )


@router.get("/{number}/diff/text", response_model=TextDiff)
def pull_text_diff(
    project_id: int,
    number: int,
    path: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Line (unified) diff of one non-L5X file in the PR; binaries report none."""
    require_member(project_id, db, user)
    pr = _get_pull(db, project_id, number)
    repo_path = files_path(path)
    return serve_diff(
        project_id,
        "text",
        pr.target_branch,
        pr.source_branch,
        lambda r, b, h: build_text_diff(r, b, h, repo_path),
        file_path=repo_path,
    )


# --- comments (PR-level and change-anchored, with one-level threading) -------
def _anchor_out(c: Comment) -> CommentAnchor | None:
    if not any((c.anchor_path, c.anchor_routine, c.anchor_rung, c.anchor_sha)):
        return None
    return CommentAnchor(
        path=c.anchor_path, routine=c.anchor_routine,
        rung=c.anchor_rung, sha=c.anchor_sha,
    )


@router.get("/{number}/comments", response_model=list[CommentOut])
def list_comments(
    project_id: int,
    number: int,
    response: Response,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[CommentOut]:
    """A PR's comments in creation order, flat (the frontend nests by
    `parent_id`). Authors are batch-loaded — no per-comment query — and the set
    is paginated via `limit`/`offset` (`X-Total-Count` header)."""
    require_member(project_id, db, user)
    pr = _get_pull(db, project_id, number)
    limit = max(1, min(limit, 500))
    total = db.scalar(
        select(func.count()).select_from(Comment).where(Comment.pull_request_id == pr.id)
    )
    comments = db.scalars(
        select(Comment)
        .where(Comment.pull_request_id == pr.id)
        .order_by(Comment.created_at.asc(), Comment.id.asc())
        .limit(limit)
        .offset(max(0, offset))
    ).all()
    umap = users_out(db, [c.author_id for c in comments])
    response.headers["X-Total-Count"] = str(total or 0)
    return [
        CommentOut(
            id=c.id,
            author=umap.get(c.author_id) or user_out(db, db.get(User, c.author_id)),
            body=c.body,
            resolved=c.resolved,
            parent_id=c.parent_id,
            anchor=_anchor_out(c),
            created_at=c.created_at,
            edited_at=c.edited_at,
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
    """Add a PR-level comment, a reply (`parent_id`), or a change-level comment
    anchored to a spot on the diff (`anchor`)."""
    require_member(project_id, db, user)
    pr = _get_pull(db, project_id, number)
    if payload.parent_id is not None:
        parent = db.scalar(
            select(Comment).where(
                Comment.id == payload.parent_id, Comment.pull_request_id == pr.id
            )
        )
        if parent is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Parent comment not found on this PR"
            )
        if parent.parent_id is not None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Replies are only one level deep"
            )
    anchor = payload.anchor or CommentAnchor()
    comment = Comment(
        pull_request_id=pr.id,
        author_id=user.id,
        parent_id=payload.parent_id,
        body=payload.body,
        anchor_path=anchor.path,
        anchor_routine=anchor.routine,
        anchor_rung=anchor.rung,
        anchor_sha=anchor.sha,
    )
    db.add(comment)
    activity.record(
        db, project_id=project_id, actor_id=user.id, verb="comment.added",
        target_type="pull", target_id=number, summary=f"commented on #{number}",
    )
    db.commit()
    db.refresh(comment)
    return CommentOut(
        id=comment.id,
        author=user_out(db, user),
        body=comment.body,
        resolved=comment.resolved,
        parent_id=comment.parent_id,
        anchor=_anchor_out(comment),
        created_at=comment.created_at,
        edited_at=comment.edited_at,
    )


@router.patch("/{number}/comments/{comment_id}", response_model=CommentOut)
def update_comment(
    project_id: int,
    number: int,
    comment_id: int,
    payload: CommentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> CommentOut:
    """Edit a comment's body (author only) and/or resolve it (any member)."""
    require_member(project_id, db, user)
    pr = _get_pull(db, project_id, number)
    comment = db.scalar(
        select(Comment).where(
            Comment.id == comment_id, Comment.pull_request_id == pr.id
        )
    )
    if comment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comment not found")
    if payload.body is not None:
        if comment.author_id != user.id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Only the author can edit a comment"
            )
        comment.body = payload.body
        comment.edited_at = datetime.now(timezone.utc)
    if payload.resolved is not None:
        comment.resolved = payload.resolved
    db.commit()
    db.refresh(comment)
    return CommentOut(
        id=comment.id,
        author=user_out(db, db.get(User, comment.author_id)),
        body=comment.body,
        resolved=comment.resolved,
        parent_id=comment.parent_id,
        anchor=_anchor_out(comment),
        created_at=comment.created_at,
        edited_at=comment.edited_at,
    )


@router.delete(
    "/{number}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_comment(
    project_id: int,
    number: int,
    comment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Delete a comment (its author or a manager). Replies cascade away."""
    require_member(project_id, db, user)
    pr = _get_pull(db, project_id, number)
    comment = db.scalar(
        select(Comment).where(
            Comment.id == comment_id, Comment.pull_request_id == pr.id
        )
    )
    if comment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comment not found")
    if comment.author_id != user.id and not _is_manager(db, project_id, user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the author or a manager can delete this comment"
        )
    db.delete(comment)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
