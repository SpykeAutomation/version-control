"""Projects, branches, commits, and diffs.

Covers: per-user repo with a main branch (#1), branch creation (#2),
diff serving for the frontend (#4), and commits with title/description (#6).
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from diff import ChangeSet, LadderDocument
from diff.ladder import LabelResolver, aoi_operand_labels, classify_rung, order_io
from diff.ladder_models import Element, RoutineLadderDiff, RungDiff
from parsers.l5x.models import AOI, Routine
from parsers.rll import RLLParseError, RLLParser
from snapshot.writer import _file_name as snapshot_file_name
from vcs import CommitLog, ProjectRepo, ProjectRepoError, TagInfo, UploadSpec

from .. import activity, audit, diff_cache, usage
from .. import comments as discussion
from ..auth import current_user
from ..config import settings
from ..db import get_db
from ..deps import membership_role, require_manager, require_member, require_owner
from ..membership import transfer_project_ownership
from ..ratelimit import client_ip, member_search_rate_limit
from ..diffing import (
    build_compare,
    build_manifest,
    build_text_diff,
    files_path,
    l5x_name,
    serve_diff,
)
from ..tree import ProjectTree, build_project_tree
from ..models import (
    Activity,
    BranchProtection,
    Comment,
    Project,
    ProjectMember,
    PullRequest,
    User,
)
from ..schemas import (
    ActivityOut,
    BranchIn,
    BranchOut,
    BranchProtectionIn,
    CommentIn,
    CommentOut,
    CommentUpdate,
    CommitDetail,
    CommitOut,
    CommitResult,
    CompareView,
    DiffManifest,
    FileEntry,
    FileListing,
    L5XSection,
    MemberCandidateOut,
    MemberIn,
    MemberOut,
    ProjectIn,
    ProjectOut,
    ProjectUpdate,
    RepositoryOverview,
    RevertIn,
    RoleUpdate,
    RoutineFullCode,
    RoutineFullLadder,
    RoutineLine,
    TagIn,
    TagOut,
    TextDiff,
    TransferIn,
)
from ..serialize import users_out
from ..serialize import user_out
from ..storage import delete_repo, locked_repo, repo_for

router = APIRouter(prefix="/projects", tags=["projects"])

# The repo's default branch. `init` creates it and PRs/overview default to it;
# branch enrichment measures ahead/behind against it, it can never be deleted,
# and it shows as protected in branch views even without a protection row
# (write-blocking protection, though, is the explicit row alone).
DEFAULT_BRANCH = "main"


def _commit_out(commit: CommitLog | None, branch: str | None = None) -> CommitOut | None:
    if commit is None:
        return None
    return CommitOut(
        sha=commit.sha,
        title=commit.title,
        description=commit.description,
        author=commit.author,
        date=commit.date,
        branch=branch,
        files_changed=commit.files_changed,
        parents=list(commit.parents),
    )


def _protection_map(db: Session, project_id: int) -> dict[str, int]:
    """branch -> required_approvals for every protection row in a project. A
    present key means the branch is explicitly protected — that's what blocks
    direct commits and member reverts. The default branch merely *displays* as
    protected without a row (and can never be deleted); writes to it stay open
    until an explicit row exists."""
    return {
        row.branch: row.required_approvals
        for row in db.scalars(
            select(BranchProtection).where(
                BranchProtection.project_id == project_id
            )
        ).all()
    }


def _branch_views(repo: ProjectRepo, db: Session, project_id: int) -> list[BranchOut]:
    """Every branch with its tip commit, default/protected flags, required
    approvals, and how far it sits ahead/behind (and whether it's merged into)
    the default branch."""
    protection = _protection_map(db, project_id)
    tips = repo.branch_tips()
    views: list[BranchOut] = []
    for name in repo.list_branches():
        is_default = name == DEFAULT_BRANCH
        tip = tips.get(name)
        ahead = behind = 0
        merged = False
        if not is_default:
            counts = repo.ahead_behind(name, DEFAULT_BRANCH)
            if counts is not None:
                ahead, behind = counts
                merged = tip is not None and ahead == 0
        views.append(
            BranchOut(
                name=name,
                is_default=is_default,
                is_protected=is_default or name in protection,
                required_approvals=protection.get(name, 0),
                latest_commit=_commit_out(tip, branch=name),
                ahead=ahead,
                behind=behind,
                merged=merged,
            )
        )
    return views


def _tag_out(repo: ProjectRepo, tag: TagInfo) -> TagOut:
    commits = repo.log(tag.target_sha, limit=1)
    return TagOut(
        name=tag.name,
        sha=tag.target_sha,
        message=tag.message,
        tagger=tag.tagger,
        date=tag.date,
        annotated=tag.annotated,
        commit=_commit_out(commits[0]) if commits else None,
    )


def _commit_label(ref: str) -> str:
    """Short, human label for a commit ref in a diff (empty tree shows as ∅)."""
    return "∅" if ref == ProjectRepo.EMPTY_TREE else ref[:7]


def _commit_base_head(project_id: int, sha: str) -> tuple[str, str]:
    """Resolve a commit ref to (base, head): its first parent (or the empty tree
    for a root commit) and itself. 404 if the commit doesn't exist."""
    repo = repo_for(project_id)
    try:
        head = repo.resolve_ref(sha)
        base = repo.commit_diff_base(head)
    except ProjectRepoError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return base, head


def _tree_compute(name: str):
    """A serve_diff compute closure that builds the organizer tree for one L5X
    file: the full structure at head, overlaid with the base..head ChangeSet."""

    def compute(repo: ProjectRepo, base_sha: str, head_sha: str) -> ProjectTree:
        doc = repo.document_at(head_sha, name)
        if doc is None:
            raise ProjectRepoError(f"no L5X file {name!r} at this ref")
        return build_project_tree(doc, repo.diff_refs(base_sha, head_sha, name))

    return compute


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "project"


def _unique_slug(db: Session, name: str, owner_id: int) -> str:
    """A slug unique among one owner's projects (append -2, -3, … on a clash).

    Routes key on the numeric id, so the slug is cosmetic; uniqueness is only
    so an owner's project URLs stay distinguishable."""
    base = _slugify(name)
    slug = base
    n = 2
    while db.scalar(
        select(Project.id).where(
            Project.owner_id == owner_id, Project.slug == slug
        )
    ):
        slug = f"{base}-{n}"
        n += 1
    return slug


def _to_out(
    db: Session, project: Project, branches: list[str], role: str | None = None
) -> ProjectOut:
    owner = user_out(db, db.get(User, project.owner_id))
    return ProjectOut(
        id=project.id,
        name=project.name,
        slug=project.slug,
        description=project.description,
        owner=owner,
        your_role=role,
        created_at=project.created_at,
        branches=branches,
    )


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> ProjectOut:
    project = Project(
        name=payload.name,
        slug=_unique_slug(db, payload.name, user.id),
        description=payload.description,
        owner_id=user.id,
    )
    db.add(project)
    db.flush()  # assign project.id
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role="owner"))
    db.commit()
    db.refresh(project)

    # Initialise the Git repo with an empty main branch.
    with locked_repo(project.id) as repo:
        repo.init(initial_branch="main")
    return _to_out(db, project, branches=["main"], role="owner")


@router.get("", response_model=list[ProjectOut])
def list_projects(
    db: Session = Depends(get_db), user: User = Depends(current_user)
) -> list[ProjectOut]:
    rows = db.execute(
        select(Project, ProjectMember.role)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(ProjectMember.user_id == user.id)
    ).all()
    out: list[ProjectOut] = []
    for project, role in rows:
        branches = repo_for(project.id).list_branches()  # read-only; no lock
        out.append(_to_out(db, project, branches, role))
    return out


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> ProjectOut:
    project = require_member(project_id, db, user)
    role = membership_role(project_id, db, user)
    branches = repo_for(project_id).list_branches()  # read-only; no lock
    return _to_out(db, project, branches, role)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> ProjectOut:
    """Rename a project or edit its description (owner/admin only)."""
    project = require_manager(project_id, db, user)
    if payload.name is not None:
        project.name = payload.name
        project.slug = _unique_slug(db, payload.name, project.owner_id)
    if payload.description is not None:
        project.description = payload.description
    db.commit()
    db.refresh(project)
    role = membership_role(project_id, db, user)
    branches = repo_for(project_id).list_branches()  # read-only; no lock
    return _to_out(db, project, branches, role)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Delete a project and everything tied to it (owner/admin only).

    Members, pull requests, and comments go via FK cascade; the Git repo and
    cached diffs are removed from disk. The project's logical bytes go back to
    the org's storage counter."""
    project = require_manager(project_id, db, user)
    usage.credit_project_deletion(db, project)
    db.delete(project)  # cascades to members, pull requests, and comments
    db.commit()
    diff_cache.clear_project(project_id)
    delete_repo(project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{project_id}/overview", response_model=RepositoryOverview)
def project_overview(
    project_id: int,
    ref: str = "main",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> RepositoryOverview:
    """One-call repository summary for the project landing page."""
    project = require_member(project_id, db, user)

    open_pulls = db.scalar(
        select(func.count())
        .select_from(PullRequest)
        .where(PullRequest.project_id == project_id, PullRequest.status == "open")
    )
    unresolved = db.scalar(
        select(func.count())
        .select_from(Comment)
        .join(PullRequest, Comment.pull_request_id == PullRequest.id)
        .where(PullRequest.project_id == project_id, Comment.resolved.is_(False))
    )

    repo = repo_for(project_id)
    files = repo.list_files(ref)
    l5x_files = [f for f in files if f.kind == "l5x"]
    commits = repo.log(ref, limit=1)

    controller_name = processor_type = firmware = None
    if l5x_files:
        controller_name, processor_type, firmware = _controller_summary(
            repo, ref, l5x_name(l5x_files[0].path)
        )

    latest = _commit_out(commits[0]) if commits else None
    tags = repo.list_tags()
    latest_release = _tag_out(repo, tags[0]) if tags else None
    return RepositoryOverview(
        id=project.id,
        name=project.name,
        description=project.description,
        file_count=len(files),
        l5x_count=len(l5x_files),
        open_pull_count=open_pulls or 0,
        unresolved_comment_count=unresolved or 0,
        controller_name=controller_name,
        processor_type=processor_type,
        firmware=firmware,
        latest_commit=latest,
        latest_release=latest_release,
    )


def _controller_summary(
    repo: ProjectRepo, ref: str, name: str
) -> tuple[str | None, str | None, str | None]:
    """(controller name, processor/model, firmware 'maj.min') for one L5X file,
    read lock-free straight from the committed controller.json snapshot."""
    try:
        raw = repo.read_blob(ref, f"l5x/{name}/snapshot/controller.json")
    except ProjectRepoError:
        return None, None, None
    try:
        controller = json.loads(raw).get("controller", {})
    except (ValueError, AttributeError):
        return None, None, None
    major, minor = controller.get("major_rev"), controller.get("minor_rev")
    firmware = f"{major}.{minor}" if major is not None else None
    return controller.get("name"), controller.get("processor_type"), firmware


@router.get("/{project_id}/members", response_model=list[MemberOut])
def list_members(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[MemberOut]:
    require_member(project_id, db, user)
    rows = db.execute(
        select(User, ProjectMember.role)
        .join(ProjectMember, ProjectMember.user_id == User.id)
        .where(ProjectMember.project_id == project_id)
    ).all()
    return [
        MemberOut(
            id=u.id, email=u.email, first_name=u.first_name,
            last_name=u.last_name, role=role,
        )
        for u, role in rows
    ]


def _project_org_id(db: Session, project: Project) -> int | None:
    """The organization a project belongs to — its owner's org (projects have
    no org column of their own; see usage.credit_project_deletion)."""
    return db.scalar(select(User.organization_id).where(User.id == project.owner_id))


def _like_fragment(q: str) -> str:
    """Quote LIKE wildcards so the user's fragment matches literally."""
    escaped = q.replace("\\", r"\\").replace("%", r"\%").replace("_", r"\_")
    return f"%{escaped}%"


@router.get("/{project_id}/member-candidates", response_model=list[MemberCandidateOut])
def member_candidates(
    project_id: int,
    q: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[MemberCandidateOut]:
    """Live search for the add-member box (owner/admin only): colleagues from
    the project's own organization who aren't members yet, matched
    case-insensitively on first name, last name, or email. Only ever searches
    that one org — other organizations' users and soft-deleted accounts are
    invisible here."""
    project = require_manager(project_id, db, user)
    member_search_rate_limit(user.id)
    q = q.strip()
    if len(q) < 2:
        return []
    org_id = _project_org_id(db, project)
    if org_id is None:
        # An org-less project has no directory to search; never fall through
        # to "all org-less users".
        return []
    fragment = _like_fragment(q)
    already = select(ProjectMember.user_id).where(
        ProjectMember.project_id == project_id
    )
    rows = db.scalars(
        select(User)
        .where(
            User.organization_id == org_id,
            User.deleted_at.is_(None),
            User.id.not_in(already),
            or_(
                User.first_name.ilike(fragment, escape="\\"),
                User.last_name.ilike(fragment, escape="\\"),
                User.email.ilike(fragment, escape="\\"),
            ),
        )
        .order_by(User.last_name, User.first_name, User.id)
        .limit(10)
    ).all()
    return [
        MemberCandidateOut(
            id=u.id, email=u.email, first_name=u.first_name,
            last_name=u.last_name, avatar=u.avatar,
        )
        for u in rows
    ]


@router.post(
    "/{project_id}/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED
)
def add_member(
    project_id: int,
    payload: MemberIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> MemberOut:
    project = require_manager(project_id, db, user)
    if payload.role not in ("member", "admin"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "role must be 'member' or 'admin'"
        )
    invitee = db.scalar(select(User).where(User.email == payload.email))
    # One 404 for "no such account", "account deleted", and "different
    # organization" alike — a manager probing emails must not be able to tell
    # which accounts exist outside their org.
    if (
        invitee is None
        or invitee.deleted_at is not None
        or invitee.organization_id != _project_org_id(db, project)
    ):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No registered user with that email"
        )
    existing = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == invitee.id,
        )
    )
    if existing is None:
        db.add(
            ProjectMember(
                project_id=project_id, user_id=invitee.id, role=payload.role
            )
        )
        db.commit()
    role = payload.role if existing is None else existing.role
    return MemberOut(
        id=invitee.id, email=invitee.email, first_name=invitee.first_name,
        last_name=invitee.last_name, role=role,
    )


def _member(db: Session, project_id: int, member_id: int) -> ProjectMember:
    membership = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == member_id,
        )
    )
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not a member of this project")
    return membership


@router.patch("/{project_id}/members/{member_id}", response_model=MemberOut)
def change_member_role(
    project_id: int,
    member_id: int,
    payload: RoleUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> MemberOut:
    """Promote/demote a member between 'member' and 'admin' (owner/admin only).
    The owner role cannot be assigned or changed here."""
    require_manager(project_id, db, user)
    if payload.role not in ("member", "admin"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "role must be 'member' or 'admin'"
        )
    membership = _member(db, project_id, member_id)
    if membership.role == "owner":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot change the owner's role")
    membership.role = payload.role
    db.commit()
    target = db.get(User, member_id)
    return MemberOut(
        id=target.id, email=target.email, first_name=target.first_name,
        last_name=target.last_name, role=membership.role,
    )


@router.delete(
    "/{project_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_member(
    project_id: int,
    member_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Remove a member (owner/admin only). The owner can't be removed, and only
    the owner may remove an admin."""
    require_manager(project_id, db, user)
    membership = _member(db, project_id, member_id)
    if membership.role == "owner":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot remove the project owner")
    if membership.role == "admin" and membership_role(project_id, db, user) != "owner":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the owner can remove an admin"
        )
    db.delete(membership)
    audit.record(
        db,
        action="project.member.removed",
        actor_id=user.id,
        target_user_id=member_id,
        target_type="membership",
        target_id=project_id,
        summary=f"removed user {member_id} from project {project_id}",
        ip=client_ip(request),
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{project_id}/transfer", response_model=MemberOut)
def transfer_ownership(
    project_id: int,
    payload: TransferIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> MemberOut:
    """Hand the project to another user (current owner only). The new owner gets
    an `owner` membership; the previous owner is demoted to `admin` so they keep
    access."""
    project = require_owner(project_id, db, user)
    new_owner = db.get(User, payload.new_owner_id)
    if new_owner is None or new_owner.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if new_owner.id == project.owner_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "That user already owns this project"
        )
    transfer_project_ownership(db, project=project, new_owner=new_owner)
    audit.record(
        db,
        action="project.ownership.transferred",
        actor_id=user.id,
        target_user_id=new_owner.id,
        target_type="project",
        target_id=project_id,
        summary=f"transferred project {project_id} to {new_owner.email}",
        ip=client_ip(request),
    )
    db.commit()
    membership = _member(db, project_id, new_owner.id)
    return MemberOut(
        id=new_owner.id, email=new_owner.email, first_name=new_owner.first_name,
        last_name=new_owner.last_name, role=membership.role,
    )


@router.get("/{project_id}/branches", response_model=list[BranchOut])
def list_branches(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[BranchOut]:
    """Every branch with its tip commit, default/protected flags, and how far it
    is ahead/behind (and whether it's merged into) the default branch."""
    require_member(project_id, db, user)
    # Tip/ahead/behind reads on refs — no lock needed.
    return _branch_views(repo_for(project_id), db, project_id)


@router.post(
    "/{project_id}/branches",
    status_code=status.HTTP_201_CREATED,
    response_model=list[BranchOut],
)
def create_branch(
    project_id: int,
    payload: BranchIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[BranchOut]:
    require_member(project_id, db, user)
    try:
        with locked_repo(project_id) as repo:
            repo.create_branch(payload.name, payload.start_point)
            views = _branch_views(repo, db, project_id)
    except ProjectRepoError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    activity.record(
        db, project_id=project_id, actor_id=user.id, verb="branch.created",
        target_type="branch", target_id=payload.name,
        summary=f"created branch {payload.name}",
    )
    db.commit()
    return views


@router.delete(
    "/{project_id}/branches/{branch:path}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_branch(
    project_id: int,
    branch: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Delete a branch (any member). The default branch and any protected branch
    cannot be deleted — unprotect it first. Deletion is permanent and may discard
    commits that were never merged."""
    require_member(project_id, db, user)
    if branch == DEFAULT_BRANCH:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "The default branch cannot be deleted"
        )
    if branch in _protection_map(db, project_id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Branch is protected — remove protection before deleting it",
        )
    try:
        with locked_repo(project_id) as repo:
            repo.delete_branch(branch, fallback=DEFAULT_BRANCH)
    except ProjectRepoError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    activity.record(
        db, project_id=project_id, actor_id=user.id, verb="branch.deleted",
        target_type="branch", target_id=branch, summary=f"deleted branch {branch}",
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/{project_id}/branches/{branch:path}/protection", response_model=BranchOut
)
def set_branch_protection(
    project_id: int,
    branch: str,
    payload: BranchProtectionIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> BranchOut:
    """Protect or unprotect a branch and set how many approvals a PR into it
    needs (owner/admin). Protection (an explicit row) blocks direct commits
    and member reverts, gates merges by `required_approvals`, and makes the
    branch undeletable. Unprotecting deletes the row and reopens all of that —
    for the DEFAULT branch that decision belongs to the project owner alone
    (an admin gets 403); once unprotected, the default branch keeps only its
    "default" tag: it still can't be deleted, but commits/reverts/merges flow
    without review like any other unprotected branch."""
    require_manager(project_id, db, user)
    required = max(0, payload.required_approvals)
    # Protection state lives in the DB; git is only consulted for existence
    # and the branch views — reads, so no lock is needed.
    repo = repo_for(project_id)
    if not repo.branch_exists(branch):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown branch: {branch}")
    if branch == DEFAULT_BRANCH and not payload.protected:
        # Owner-only: reopening direct writes to the default branch is the
        # project owner's call, not an admin's. Without this, protecting the
        # default branch once would lock direct commits out forever (the row
        # used to be permanent) — protection must stay reversible.
        require_owner(project_id, db, user)
    existing = db.scalar(
        select(BranchProtection).where(
            BranchProtection.project_id == project_id,
            BranchProtection.branch == branch,
        )
    )
    if not payload.protected:
        if existing is not None:
            db.delete(existing)
    elif existing is not None:
        existing.required_approvals = required
    else:
        db.add(
            BranchProtection(
                project_id=project_id, branch=branch, required_approvals=required
            )
        )
    db.commit()
    views = _branch_views(repo, db, project_id)
    for view in views:
        if view.name == branch:
            return view
    raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown branch: {branch}")


@router.post(
    "/{project_id}/commits",
    response_model=CommitResult,
    status_code=status.HTTP_201_CREATED,
)
def upload_files(
    project_id: int,
    branch: str = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> CommitResult:
    """Upload one or more files as a single commit.

    L5X files are parsed and snapshotted (their raw bytes kept for download);
    any other file is stored as-is. A single `files` part works too. The upload
    is atomic: if any L5X is malformed, nothing is committed. Each file is capped
    at `PLCVC_MAX_UPLOAD_MB` (the Caddy edge caps the whole request separately).

    An explicitly protected branch takes no direct commits — changes reach it
    through a pull request (branch + PR is the supported flow; the frontend's
    UI gating is reinforcement, this check is the enforcement). The default
    branch's *implicit* protection deliberately does NOT block commits: a
    project with no protection rows works straight on main.
    """
    require_member(project_id, db, user)
    if branch in _protection_map(db, project_id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Branch is protected — commit via a pull request",
        )

    limit = settings.max_upload_bytes
    tmp_paths: list[str] = []
    specs: list[UploadSpec] = []
    try:
        for upload in files:
            name = upload.filename or "upload"
            # Fast reject: the multipart parser reports each part's size, so an
            # oversized file gets its 413 before we spool a copy of it. The
            # in-copy cap in _spool_capped stays as the fallback for parsers
            # that don't report a size.
            if upload.size is not None and upload.size > limit:
                raise HTTPException(
                    status.HTTP_413_CONTENT_TOO_LARGE,
                    f"{name!r} exceeds the {settings.max_upload_mb} MB per-file limit",
                )
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=Path(name).suffix
            ) as tmp:
                tmp_paths.append(tmp.name)
                _spool_capped(upload, tmp, limit, name)
            specs.append(UploadSpec(local_path=Path(tmp.name), filename=name))
        incoming = sum(os.path.getsize(p) for p in tmp_paths)
        # Reserve the bytes against the org quota (507 if they don't fit); if
        # the Git work then fails for any reason, give the reservation back.
        usage.reserve(db, user, incoming)
        try:
            with locked_repo(project_id) as repo:
                info = repo.commit_files(
                    specs,
                    branch=branch,
                    title=title,
                    description=description,
                    author_name=f"{user.first_name} {user.last_name}".strip(),
                    author_email=user.email,
                )
        except BaseException:
            usage.release(db, user, incoming)
            raise
    except ProjectRepoError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    finally:
        for path in tmp_paths:
            try:
                os.unlink(path)
            except OSError:
                pass
    usage.add_project_bytes(db, project_id, incoming)
    activity.record(
        db, project_id=project_id, actor_id=user.id, verb="commit.pushed",
        target_type="commit", target_id=info.sha[:12],
        summary=f"committed to {branch}: {title}",
    )
    db.commit()
    return CommitResult(sha=info.sha, branch=info.branch, title=info.title)


_UPLOAD_CHUNK = 1024 * 1024  # 1 MB


def _spool_capped(upload: UploadFile, dest, limit: int, name: str) -> None:
    """Copy an upload to `dest`, aborting with 413 once it exceeds `limit` bytes.

    Starlette has already buffered the whole multipart body before we get here
    (so the real ingress guard is Caddy's request_body limit); this enforces the
    precise *per-file* cap and returns a clean error without writing the
    oversized file into our data dir.
    """
    written = 0
    while chunk := upload.file.read(_UPLOAD_CHUNK):
        written += len(chunk)
        if written > limit:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                f"{name!r} exceeds the {settings.max_upload_mb} MB per-file limit",
            )
        dest.write(chunk)


@router.post(
    "/{project_id}/revert",
    response_model=CommitResult,
    status_code=status.HTTP_201_CREATED,
)
def revert_branch(
    project_id: int,
    payload: RevertIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> CommitResult:
    """Restore the repo state of `target_sha` as ONE new commit on `branch`.

    History is never rewritten: every commit between the target and the tip is
    preserved, and the new commit's tree is byte-identical to the target's —
    so diffing the new commit against its parent automatically shows the
    inverse of everything since the target. There is deliberately no preview
    endpoint: preview with the existing diff endpoints (`/diff`, `/compare`,
    `/tree`, per-file views) using base=<current tip>, head=<target>; the
    `expected_tip_sha` precondition then guarantees the confirmed preview is
    what actually gets reverted — 409 (with the current tip) when the branch
    has moved, and the client refreshes.

    Permissions mirror committing: an unprotected branch reverts like it
    commits — any member. A protected branch (which rejects direct commits;
    change flows through a PR) can still be reverted, but only by an
    owner/admin: revert is the sanctioned emergency rollback, and it can't
    wait on the PR loop — so it trades the member gate for the manager gate.
    """
    require_member(project_id, db, user)
    if not repo_for(project_id).branch_exists(payload.branch):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Unknown branch: {payload.branch}"
        )
    if payload.branch in _protection_map(db, project_id):
        require_manager(project_id, db, user)  # 403 for a plain member
    # Check-then-write under the per-project write lock: the tip comparison
    # and the ref move must see the same repo state. The frontend's disabled
    # button is reinforcement; this is the enforcement. (restore_commit's
    # compare-and-swap ref move is belt and braces on top.)
    try:
        with locked_repo(project_id) as repo:
            target_log = repo.log(payload.target_sha, limit=1)
            if not target_log:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, "Target commit not found"
                )
            target = target_log[0].sha
            try:
                expected = repo.resolve_ref(payload.expected_tip_sha)
            except ProjectRepoError as exc:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
            tip = repo.resolve_ref(payload.branch)
            if tip != expected:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    f"Branch has moved: the tip is now {tip}",
                )
            if target == tip:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, "Target is already the branch tip"
                )
            if not repo.is_ancestor(target, tip):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "Target is not an ancestor of the branch tip",
                )
            if repo.resolve_ref(f"{target}^{{tree}}") == repo.resolve_ref(
                f"{tip}^{{tree}}"
            ):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "Nothing to revert — the branch already matches the target",
                )
            message = (
                payload.message
                or f'Revert to {target[:7]} "{target_log[0].title}"'
            )
            new_sha = repo.restore_commit(
                payload.branch,
                target,
                tip,
                title=message,
                description=payload.description or "",
                author_name=f"{user.first_name} {user.last_name}".strip(),
                author_email=user.email,
            )
    except ProjectRepoError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    activity.record(
        db, project_id=project_id, actor_id=user.id, verb="commit.reverted",
        target_type="commit", target_id=new_sha[:12],
        summary=f"reverted {payload.branch} to {target[:7]}",
    )
    db.commit()
    return CommitResult(
        sha=new_sha, branch=payload.branch, title=message.splitlines()[0]
    )


@router.get("/{project_id}/commits", response_model=list[CommitOut])
def list_commits(
    project_id: int,
    response: Response,
    branch: str = "main",
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[CommitOut]:
    """Commit history for a branch, newest first. Each commit is tagged with the
    `branch` it was listed under and a `files_changed` count (vs its parent).
    Paginated via `limit`/`offset`, with the branch's total in `X-Total-Count`."""
    require_member(project_id, db, user)
    limit = max(1, min(limit, 200))
    repo = repo_for(project_id)  # history reads — no lock needed
    commits = repo.log(branch, limit=limit, offset=max(0, offset))
    total = repo.commit_total(branch)
    response.headers["X-Total-Count"] = str(total)
    return [_commit_out(c, branch=branch) for c in commits]


@router.get("/{project_id}/commits/{sha}", response_model=CommitDetail)
def commit_detail(
    project_id: int,
    sha: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> CommitDetail:
    """One commit plus the files it changed vs its first parent (the root commit
    diffs against the empty tree, so its whole content shows as added)."""
    require_member(project_id, db, user)
    repo = repo_for(project_id)  # immutable-commit reads — no lock needed
    commits = repo.log(sha, limit=1)
    if not commits:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Commit not found")
    commit = commits[0]
    parent = repo.commit_parent(commit.sha)
    base = parent if parent is not None else repo.EMPTY_TREE
    manifest = build_manifest(repo, base, commit.sha)
    return CommitDetail(
        sha=commit.sha,
        title=commit.title,
        description=commit.description,
        author=commit.author,
        date=commit.date,
        parent=parent,
        files_changed=len(manifest.files),
        files=manifest.files,
    )


@router.get("/{project_id}/commits/{sha}/diff/changeset", response_model=ChangeSet)
def commit_changeset(
    project_id: int,
    sha: str,
    path: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Semantic diff of one L5X file introduced by a commit (parent -> commit)."""
    require_member(project_id, db, user)
    base, head = _commit_base_head(project_id, sha)
    name = l5x_name(path)
    return serve_diff(
        project_id,
        "changeset",
        base,
        head,
        lambda r, b, h: r.diff_refs(b, h, name),
        file_path=f"l5x/{name}",
    )


@router.get("/{project_id}/commits/{sha}/diff/ladder", response_model=LadderDocument)
def commit_ladder_diff(
    project_id: int,
    sha: str,
    path: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Drawable ladder-diagram diff of one L5X file in a commit (parent -> commit)."""
    require_member(project_id, db, user)
    base, head = _commit_base_head(project_id, sha)
    name = l5x_name(path)
    return serve_diff(
        project_id,
        "ladder",
        base,
        head,
        lambda r, b, h: r.ladder_diff_refs(
            b, h, name, old_label=_commit_label(b), new_label=_commit_label(h)
        ),
        file_path=f"l5x/{name}",
    )


@router.get("/{project_id}/commits/{sha}/diff/text", response_model=TextDiff)
def commit_text_diff(
    project_id: int,
    sha: str,
    path: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Line (unified) diff of one non-L5X file in a commit; binaries report none."""
    require_member(project_id, db, user)
    base, head = _commit_base_head(project_id, sha)
    repo_path = files_path(path)
    return serve_diff(
        project_id,
        "text",
        base,
        head,
        lambda r, b, h: build_text_diff(r, b, h, repo_path),
        file_path=repo_path,
    )


@router.get("/{project_id}/commits/{sha}/tree", response_model=ProjectTree)
def commit_tree(
    project_id: int,
    sha: str,
    path: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Organizer tree of one L5X file as of a commit (the Studio 5000 Controller
    Organizer with per-node change status vs the commit's first parent; a root
    commit reads as everything added). `path` is an `l5x/<name>` manifest path."""
    require_member(project_id, db, user)
    base, head = _commit_base_head(project_id, sha)
    name = l5x_name(path)
    return serve_diff(
        project_id, "tree", base, head, _tree_compute(name), file_path=f"l5x/{name}"
    )


@lru_cache(maxsize=1)
def _rll_parser() -> RLLParser:
    """Building a parser compiles its grammar (slow), so build it once per
    process; parsing never mutates it, so sharing across requests is safe."""
    return RLLParser()


def _routine_blob_path(l5x: str, program: str, routine: str) -> str:
    """Snapshot path of one routine's JSON. Program and routine become file
    names via the snapshot writer's escaping, so Windows-reserved names
    (e.g. AUX -> AUX-) resolve to the blob that was actually committed."""
    return (
        f"l5x/{l5x}/snapshot/programs/{snapshot_file_name(program)}"
        f"/routines/{snapshot_file_name(routine)}.json"
    )


def _aoi_labels_at(repo: ProjectRepo, ref: str, name: str) -> dict[str, list[str]]:
    """Operand-row labels for one L5X file's AOIs at a ref, read lock-free from
    the snapshot's aois/*.json (the same definitions the ladder-diff path loads).
    A missing or unreadable AOI file only costs its labels, never the request."""
    base = f"l5x/{name}/snapshot/aois"
    aois: list[AOI] = []
    for entry in repo.tree_names(ref, base):
        if not entry.endswith(".json"):
            continue
        try:
            aois.append(AOI.model_validate(json.loads(repo.read_blob(ref, f"{base}/{entry}"))))
        except (ProjectRepoError, ValueError):
            continue
    return aoi_operand_labels(aois)


def _full_rung_elements(
    text: str | None, parser: RLLParser, resolver: LabelResolver
) -> list[Element]:
    """Drawable elements for one committed rung, laid out reads-left /
    writes-right like the diff views. A rung the grammar cannot read renders
    verbatim as a raw element rather than failing the whole routine."""
    if not text:
        return []
    try:
        parsed = parser.parse(text)
    except RLLParseError:
        return [Element(kind="raw", text=text)]
    return order_io(classify_rung(parsed, resolver), resolver)


@router.get(
    "/{project_id}/commits/{sha}/routine",
    response_model=RoutineFullLadder | RoutineFullCode,
)
def commit_routine(
    project_id: int,
    sha: str,
    program: str,
    routine: str,
    path: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> RoutineFullLadder | RoutineFullCode:
    """The full content of one routine as it exists at a commit — not a diff.

    Read lock-free from the committed snapshot (one small blob + the AOI
    definitions for operand labels). A ladder routine returns the ladder-diff
    IR with every rung "unchanged" and only the `after` side filled, so the
    frontend renders it single-column with the same LadderDiff renderer; an
    ST routine returns its numbered lines. `path` (an `l5x/<name>` manifest
    path) pins the L5X file; without it every L5X file at the commit is
    probed. Encoded (source-protected) routines and types without parsed
    content (FBD/SFC) are 404 — the frontend shows its placeholder."""
    require_member(project_id, db, user)
    repo = repo_for(project_id)  # immutable-commit reads — no lock needed
    try:
        head = repo.resolve_ref(sha)
    except ProjectRepoError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))

    names = [l5x_name(path)] if path else repo.tree_names(head, "l5x")
    name = raw = None
    for candidate in names:
        try:
            raw = repo.read_blob(head, _routine_blob_path(candidate, program, routine))
            name = candidate
            break
        except ProjectRepoError:
            continue
    if raw is None or name is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Routine not found at this commit")

    try:
        rt = Routine.model_validate(json.loads(raw))
    except ValueError:  # covers JSONDecodeError and pydantic's ValidationError
        raise HTTPException(status.HTTP_404_NOT_FOUND, "routine content not available")

    label = head[:7]
    if rt.encoded:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "routine content not available (source-protected)",
        )
    if rt.type == "ST" and rt.content.lines is not None:
        return RoutineFullCode(
            ref=label,
            lines=[
                RoutineLine(ln=i, text=line.text)
                for i, line in enumerate(rt.content.lines, start=1)
            ],
        )
    if rt.type != "RLL" or rt.content.rungs is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "routine content not available")

    parser = _rll_parser()
    resolver = LabelResolver(aoi_operands=_aoi_labels_at(repo, head, name))
    rungs = [
        RungDiff(
            status="unchanged",
            new_number=rung.number,
            new_comment=rung.comment,
            before=[],
            after=_full_rung_elements(rung.text, parser, resolver),
        )
        for rung in rt.content.rungs
    ]
    return RoutineFullLadder(
        ladder=RoutineLadderDiff(
            controller=_controller_summary(repo, head, name)[0],
            program=program,
            routine=routine,
            routine_type=rt.type,
            new_label=label,
            rungs=rungs,
        )
    )


# --- commit-page discussions --------------------------------------------------
# Same table and behavior as PR comments (app/comments.py) — flat list, replies
# at any depth, anchors, author-only edits, author-or-manager deletes with
# subtree cascade — scoped to (project, commit) instead of a PR.


def _commit_scope(repo: ProjectRepo, project_id: int, sha: str) -> tuple[str, list]:
    """Resolve `sha` (any commit-ish; 404 when it names no commit here) to the
    full commit id plus the comment scope for it. Comments are always stored
    under the full sha, so short-ref and full-sha lookups converge."""
    full = repo.commit_sha(sha)
    if full is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Commit not found")
    return full, [Comment.project_id == project_id, Comment.commit_sha == full]


@router.get("/{project_id}/commits/{sha}/comments", response_model=list[CommentOut])
def list_commit_comments(
    project_id: int,
    sha: str,
    response: Response,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[CommentOut]:
    """A commit's discussion in creation order, flat (the frontend nests by
    `parent_id`); paginated via `limit`/`offset` (`X-Total-Count` header)."""
    require_member(project_id, db, user)
    _, scope = _commit_scope(repo_for(project_id), project_id, sha)
    return discussion.list_comments(db, response, scope, limit=limit, offset=offset)


@router.post(
    "/{project_id}/commits/{sha}/comments",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
)
def add_commit_comment(
    project_id: int,
    sha: str,
    payload: CommentIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> CommentOut:
    """Add a comment to a commit's discussion — top-level, a reply
    (`parent_id`, any depth; the parent must belong to the same commit's
    discussion), or anchored to a spot on the rendered change (`anchor`)."""
    require_member(project_id, db, user)
    full, scope = _commit_scope(repo_for(project_id), project_id, sha)
    comment = discussion.create_comment(
        db, user, payload, scope, "commit",
        project_id=project_id, commit_sha=full,
    )
    activity.record(
        db, project_id=project_id, actor_id=user.id, verb="comment.added",
        target_type="commit", target_id=full[:12],
        summary=f"commented on commit {full[:7]}",
    )
    db.commit()
    db.refresh(comment)
    return discussion.comment_out(db, comment, user_out(db, user))


@router.patch(
    "/{project_id}/commits/{sha}/comments/{comment_id}", response_model=CommentOut
)
def update_commit_comment(
    project_id: int,
    sha: str,
    comment_id: int,
    payload: CommentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> CommentOut:
    """Edit a comment's body (author only) and/or resolve it (any member)."""
    require_member(project_id, db, user)
    _, scope = _commit_scope(repo_for(project_id), project_id, sha)
    comment = discussion.get_comment(db, comment_id, scope)
    discussion.apply_update(comment, payload, user)
    db.commit()
    db.refresh(comment)
    return discussion.comment_out(db, comment)


@router.delete(
    "/{project_id}/commits/{sha}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_commit_comment(
    project_id: int,
    sha: str,
    comment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Delete a comment (its author or a manager). The whole reply subtree
    cascades away with it."""
    require_member(project_id, db, user)
    _, scope = _commit_scope(repo_for(project_id), project_id, sha)
    comment = discussion.get_comment(db, comment_id, scope)
    discussion.ensure_can_delete(db, project_id, user, comment)
    db.delete(comment)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{project_id}/diff", response_model=DiffManifest)
def diff_manifest(
    project_id: int,
    base: str,
    head: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """List the files that changed between two refs (drill in per file below)."""
    require_member(project_id, db, user)
    return serve_diff(project_id, "manifest", base, head, build_manifest)


@router.get("/{project_id}/compare", response_model=CompareView)
def compare_refs(
    project_id: int,
    base: str,
    head: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """One-call Compare view model for two refs: rolled-up summary counts (files,
    rungs, routines, tags, commits), per-file impact rows, and the affected
    symbols. Cached by the commit pair like any diff. Reuse for a PR's change
    summary by passing its target/source branches."""
    require_member(project_id, db, user)
    return serve_diff(project_id, "compare", base, head, build_compare)


@router.get("/{project_id}/diff/changeset", response_model=ChangeSet)
def diff_changeset(
    project_id: int,
    base: str,
    head: str,
    path: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Semantic diff of one L5X file (the code/text panel)."""
    require_member(project_id, db, user)
    name = l5x_name(path)
    return serve_diff(
        project_id,
        "changeset",
        base,
        head,
        lambda r, b, h: r.diff_refs(b, h, name),
        file_path=f"l5x/{name}",
    )


@router.get("/{project_id}/diff/ladder", response_model=LadderDocument)
def diff_ladder(
    project_id: int,
    base: str,
    head: str,
    path: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Drawable ladder-diagram diff of one L5X file (the visual panel)."""
    require_member(project_id, db, user)
    name = l5x_name(path)
    return serve_diff(
        project_id,
        "ladder",
        base,
        head,
        lambda r, b, h: r.ladder_diff_refs(b, h, name, old_label=base, new_label=head),
        file_path=f"l5x/{name}",
    )


@router.get("/{project_id}/diff/text", response_model=TextDiff)
def diff_text(
    project_id: int,
    base: str,
    head: str,
    path: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Line (unified) diff of one non-L5X file; binary files report no diff."""
    require_member(project_id, db, user)
    repo_path = files_path(path)
    return serve_diff(
        project_id,
        "text",
        base,
        head,
        lambda r, b, h: build_text_diff(r, b, h, repo_path),
        file_path=repo_path,
    )


@router.get("/{project_id}/tree", response_model=ProjectTree)
def project_tree(
    project_id: int,
    base: str,
    head: str,
    path: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Organizer tree of one L5X file at `head`, tagged by the base..head diff.

    The full Controller Organizer (Controller -> Tasks / Programs / Routines,
    plus AOIs, Data Types, Controller Tags, I/O) with each node flagged
    added/removed/modified/unchanged. Nested under the file tree: `path` is an
    `l5x/<name>` entry from `GET /files`. Routine nodes carry (controller,
    program, routine) so the UI can link them to their ladder-diff card."""
    require_member(project_id, db, user)
    name = l5x_name(path)
    return serve_diff(
        project_id, "tree", base, head, _tree_compute(name), file_path=f"l5x/{name}"
    )


# The sections of a parsed L5X file the organizer's detail tables can request.
L5XSectionName = Literal["controller", "datatypes", "tags", "modules", "aoi"]

# Heavy per-entity fields excluded from the list sections, measured on a real
# 16.5 MB production export (351 UDTs / 193 tags / 32 modules): tags drop from
# 1.36 MB to 91 KB without value/comment/MSG blobs; modules from 78 KB to
# 28 KB without config/connection blobs. Per-entity detail that needs the
# excluded fields can be added later the way section=aoi already works.
_L5X_TAG_EXCLUDE = {"values", "comments", "message_config"}
_L5X_MODULE_EXCLUDE = {
    "config_values", "connections", "rack_connections", "extended_properties",
}


def _l5x_section_compute(name: str, section: str, aoi_name: str | None):
    """A serve_diff compute closure for one section of one L5X file at a ref.

    Reads the already-parsed document at head (base == head: a snapshot is a
    pure function of a single commit) and serializes the section straight from
    the parser models — no new schemas."""

    def compute(repo: ProjectRepo, base_sha: str, head_sha: str) -> L5XSection:
        doc = repo.document_at(head_sha, name)
        if doc is None:
            raise ProjectRepoError(f"no L5X file {name!r} at this ref")
        if section == "controller":
            data = doc.controller.model_dump(mode="json")
        elif section == "datatypes":
            data = [d.model_dump(mode="json") for d in doc.data_types]
        elif section == "tags":
            data = [
                t.model_dump(mode="json", exclude=_L5X_TAG_EXCLUDE)
                for t in doc.controller_tags
            ]
        elif section == "modules":
            data = [
                m.model_dump(mode="json", exclude=_L5X_MODULE_EXCLUDE)
                for m in doc.modules
            ]
        else:  # aoi — one full definition (params, local tags, routine content)
            aoi = next(
                (a for a in doc.add_on_instructions if a.name == aoi_name), None
            )
            if aoi is None:
                raise ProjectRepoError(f"no AOI {aoi_name!r} in {name!r} at this ref")
            data = aoi.model_dump(mode="json")
        return L5XSection(section=section, data=data)

    return compute


@router.get("/{project_id}/l5x", response_model=L5XSection)
def l5x_section(
    project_id: int,
    ref: str,
    path: str,
    section: L5XSectionName,
    name: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """One raw section of a parsed L5X file at a ref — the data behind the
    organizer's detail tables (UDT members, AOI parameters/routines, the
    controller-tag grid, the I/O module table, controller properties).

    `path` is an `l5x/<name>` manifest path. `section=aoi` returns ONE full
    AOI and requires `&name=`; the whole AOI list is deliberately not offered
    (812 KB+ on a real export — per-AOI is ~13 KB). List sections exclude the
    measured-heavy per-entity fields (see the exclusion sets above and the
    README contract). Parsing a large export costs ~0.4 s, so responses are
    served through the sha-keyed disk cache like every diff view."""
    require_member(project_id, db, user)
    if section == "aoi" and not name:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "section=aoi requires &name=<AOI name>"
        )
    l5x = l5x_name(path)
    file_key = f"l5x/{l5x}#aoi:{name}" if section == "aoi" else f"l5x/{l5x}#{section}"
    return serve_diff(
        project_id,
        "l5x-section",
        ref,
        ref,
        _l5x_section_compute(l5x, section, name),
        file_path=file_key,
    )


@router.get("/{project_id}/files", response_model=FileListing)
def list_files(
    project_id: int,
    ref: str = "main",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> FileListing:
    """The project's files at a ref (empty before the first commit).

    Non-L5X files keep their uploaded folder structure (e.g. files/docs/io.csv);
    each entry includes its size and who last changed it and when."""
    require_member(project_id, db, user)
    repo = repo_for(project_id)
    entries = repo.list_files(ref, with_history=True)
    return FileListing(
        files=[
            FileEntry(
                path=e.path,
                kind=e.kind,
                size=e.size,
                modified_by=e.modified_by,
                modified_at=e.modified_at,
            )
            for e in entries
        ]
    )


@router.get("/{project_id}/files/raw")
def download_file(
    project_id: int,
    ref: str,
    path: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Download a tracked file's exact bytes as of a ref (e.g. the original L5X)."""
    require_member(project_id, db, user)
    p = path.strip().lstrip("/")
    if ".." in p.split("/") or not (p.startswith("l5x/") or p.startswith("files/")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"invalid file path: {path!r}")
    repo = repo_for(project_id)
    try:
        data = repo.read_blob(ref, p)
    except ProjectRepoError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if p.startswith("l5x/") and p.endswith("/source.L5X"):
        filename = p.split("/")[1] + ".L5X"  # e.g. l5x/Line1/source.L5X -> Line1.L5X
    else:
        filename = Path(p).name
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- tags / releases ---
@router.get("/{project_id}/tags", response_model=list[TagOut])
def list_tags(
    project_id: int,
    response: Response,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[TagOut]:
    """Tags, newest first — they back the Tags card; the first is the latest
    release. Each carries its notes, tagger, date, and tagged-commit summary.
    Paginated via `limit`/`offset`, with the total in `X-Total-Count`."""
    require_member(project_id, db, user)
    limit = max(1, min(limit, 200))
    start = max(0, offset)
    repo = repo_for(project_id)  # tag/ref reads — no lock needed
    tags = repo.list_tags()
    page = tags[start:start + limit]
    out = [_tag_out(repo, tag) for tag in page]
    response.headers["X-Total-Count"] = str(len(tags))
    return out


@router.post(
    "/{project_id}/tags", response_model=TagOut, status_code=status.HTTP_201_CREATED
)
def create_tag(
    project_id: int,
    payload: TagIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> TagOut:
    """Cut a tag/release at a ref (any member). A non-empty `message` makes an
    annotated tag attributed to you, with the message as release notes."""
    require_member(project_id, db, user)
    try:
        with locked_repo(project_id) as repo:
            tag = repo.create_tag(
                payload.name,
                payload.ref,
                message=payload.message,
                tagger_name=f"{user.first_name} {user.last_name}".strip(),
                tagger_email=user.email,
            )
            out = _tag_out(repo, tag)
    except ProjectRepoError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    activity.record(
        db, project_id=project_id, actor_id=user.id, verb="tag.created",
        target_type="tag", target_id=payload.name,
        summary=f"released {payload.name}",
    )
    db.commit()
    return out


@router.delete(
    "/{project_id}/tags/{name:path}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_tag(
    project_id: int,
    name: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Delete a tag/release (owner/admin)."""
    require_manager(project_id, db, user)
    try:
        with locked_repo(project_id) as repo:
            repo.delete_tag(name)
    except ProjectRepoError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    activity.record(
        db, project_id=project_id, actor_id=user.id, verb="tag.deleted",
        target_type="tag", target_id=name, summary=f"deleted tag {name}",
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- activity feed / audit log ---
@router.get("/{project_id}/activity", response_model=list[ActivityOut])
def list_activity(
    project_id: int,
    response: Response,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[ActivityOut]:
    """The project's activity feed / audit log, newest first. One indexed query
    on (project_id, created_at); paginated via `limit`/`offset` with the total in
    `X-Total-Count`."""
    require_member(project_id, db, user)
    limit = max(1, min(limit, 200))
    total = db.scalar(
        select(func.count()).select_from(Activity).where(Activity.project_id == project_id)
    )
    events = db.scalars(
        select(Activity)
        .where(Activity.project_id == project_id)
        .order_by(Activity.created_at.desc(), Activity.id.desc())
        .limit(limit)
        .offset(max(0, offset))
    ).all()
    umap = users_out(db, [e.actor_id for e in events if e.actor_id is not None])
    response.headers["X-Total-Count"] = str(total or 0)
    return [
        ActivityOut(
            id=e.id,
            actor=umap.get(e.actor_id),
            verb=e.verb,
            target_type=e.target_type,
            target_id=e.target_id,
            summary=e.summary,
            created_at=e.created_at,
        )
        for e in events
    ]
