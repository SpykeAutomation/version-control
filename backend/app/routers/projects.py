"""Projects, branches, commits, and diffs.

Covers: per-user repo with a main branch (#1), branch creation (#2),
diff serving for the frontend (#4), and commits with title/description (#6).
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from diff import ChangeSet, LadderDocument
from vcs import CommitLog, ProjectRepo, ProjectRepoError, TagInfo, UploadSpec

from .. import activity, diff_cache, usage
from ..auth import current_user
from ..config import settings
from ..db import get_db
from ..deps import membership_role, require_manager, require_member
from ..diffing import (
    build_compare,
    build_manifest,
    build_text_diff,
    files_path,
    l5x_name,
    serve_diff,
)
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
    CommitDetail,
    CommitOut,
    CommitResult,
    CompareView,
    DiffManifest,
    FileEntry,
    FileListing,
    MemberIn,
    MemberOut,
    ProjectIn,
    ProjectOut,
    ProjectUpdate,
    RepositoryOverview,
    RoleUpdate,
    TagIn,
    TagOut,
    TextDiff,
)
from ..serialize import users_out
from ..serialize import user_out
from ..storage import delete_repo, locked_repo, repo_for

router = APIRouter(prefix="/projects", tags=["projects"])

# The repo's default branch. `init` creates it and PRs/overview default to it;
# branch enrichment measures ahead/behind against it and it is always protected.
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
    )


def _protection_map(db: Session, project_id: int) -> dict[str, int]:
    """branch -> required_approvals for every protection row in a project. A
    present key means the branch is explicitly protected; the default branch is
    also protected even without a row (with 0 required approvals unless one)."""
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
        with locked_repo(project.id) as repo:
            branches = repo.list_branches()
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
    with locked_repo(project_id) as repo:
        branches = repo.list_branches()
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
    with locked_repo(project_id) as repo:
        branches = repo.list_branches()
    return _to_out(db, project, branches, role)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Delete a project and everything tied to it (owner/admin only).

    Members, pull requests, and comments go via FK cascade; the Git repo and
    cached diffs are removed from disk."""
    project = require_manager(project_id, db, user)
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


@router.post(
    "/{project_id}/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED
)
def add_member(
    project_id: int,
    payload: MemberIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> MemberOut:
    require_manager(project_id, db, user)
    if payload.role not in ("member", "admin"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "role must be 'member' or 'admin'"
        )
    invitee = db.scalar(select(User).where(User.email == payload.email))
    if invitee is None:
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
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{project_id}/branches", response_model=list[BranchOut])
def list_branches(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[BranchOut]:
    """Every branch with its tip commit, default/protected flags, and how far it
    is ahead/behind (and whether it's merged into) the default branch."""
    require_member(project_id, db, user)
    with locked_repo(project_id) as repo:
        return _branch_views(repo, db, project_id)


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
    needs (owner/admin). A protected branch can't be deleted via the API. The
    default branch is always protected — you can still set its required
    approvals, but you can't unprotect it."""
    require_manager(project_id, db, user)
    required = max(0, payload.required_approvals)
    with locked_repo(project_id) as repo:
        if not repo.branch_exists(branch):
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown branch: {branch}")
        if branch == DEFAULT_BRANCH and not payload.protected:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "The default branch is always protected",
            )
        existing = db.scalar(
            select(BranchProtection).where(
                BranchProtection.project_id == project_id,
                BranchProtection.branch == branch,
            )
        )
        # The default branch is protected even with no row, but a row lets it
        # carry required_approvals; drop the row only for a non-default branch.
        if not payload.protected and branch != DEFAULT_BRANCH:
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
    """
    require_member(project_id, db, user)

    limit = settings.max_upload_bytes
    tmp_paths: list[str] = []
    specs: list[UploadSpec] = []
    try:
        for upload in files:
            name = upload.filename or "upload"
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=Path(name).suffix
            ) as tmp:
                tmp_paths.append(tmp.name)
                _spool_capped(upload, tmp, limit, name)
            specs.append(UploadSpec(local_path=Path(tmp.name), filename=name))
        incoming = sum(os.path.getsize(p) for p in tmp_paths)
        if usage.org_usage_bytes(db, user) + incoming > settings.org_storage_limit_bytes:
            raise HTTPException(
                status.HTTP_507_INSUFFICIENT_STORAGE,
                f"Organization storage limit of {settings.org_storage_limit_gb} GB "
                "reached",
            )
        with locked_repo(project_id) as repo:
            info = repo.commit_files(
                specs,
                branch=branch,
                title=title,
                description=description,
                author_name=f"{user.first_name} {user.last_name}".strip(),
                author_email=user.email,
            )
    except ProjectRepoError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    finally:
        for path in tmp_paths:
            try:
                os.unlink(path)
            except OSError:
                pass
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
    with locked_repo(project_id) as repo:
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
    with locked_repo(project_id) as repo:
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
    with locked_repo(project_id) as repo:
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
