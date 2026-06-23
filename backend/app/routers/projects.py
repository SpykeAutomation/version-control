"""Projects, branches, commits, and diffs.

Covers: per-user repo with a main branch (#1), branch creation (#2),
diff serving for the frontend (#4), and commits with title/description (#6).
"""
from __future__ import annotations

import os
import re
import shutil
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
from sqlalchemy import select
from sqlalchemy.orm import Session

from diff import ChangeSet, LadderDocument
from vcs import ProjectRepoError

from ..auth import current_user
from ..db import get_db
from ..deps import require_member
from ..diffing import serve_diff
from ..models import Project, ProjectMember, User
from ..schemas import (
    BranchIn,
    CommitOut,
    CommitResult,
    MemberIn,
    MemberOut,
    ProjectIn,
    ProjectOut,
)
from ..storage import locked_repo

router = APIRouter(prefix="/projects", tags=["projects"])


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "project"


def _to_out(project: Project, branches: list[str]) -> ProjectOut:
    return ProjectOut.model_validate(project).model_copy(update={"branches": branches})


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> ProjectOut:
    project = Project(
        name=payload.name, slug=_slugify(payload.name), owner_id=user.id
    )
    db.add(project)
    db.flush()  # assign project.id
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role="owner"))
    db.commit()
    db.refresh(project)

    # Initialise the Git repo with an empty main branch.
    with locked_repo(project.id) as repo:
        repo.init(initial_branch="main")
    return _to_out(project, branches=["main"])


@router.get("", response_model=list[ProjectOut])
def list_projects(
    db: Session = Depends(get_db), user: User = Depends(current_user)
) -> list[ProjectOut]:
    projects = db.scalars(
        select(Project)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(ProjectMember.user_id == user.id)
    ).all()
    out: list[ProjectOut] = []
    for project in projects:
        with locked_repo(project.id) as repo:
            branches = repo.list_branches()
        out.append(_to_out(project, branches))
    return out


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> ProjectOut:
    project = require_member(project_id, db, user)
    with locked_repo(project_id) as repo:
        branches = repo.list_branches()
    return _to_out(project, branches)


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
        MemberOut(id=u.id, email=u.email, name=u.name, role=role) for u, role in rows
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
    project = require_member(project_id, db, user)
    if project.owner_id != user.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the project owner can add members"
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
    return MemberOut(id=invitee.id, email=invitee.email, name=invitee.name, role=role)


@router.get("/{project_id}/branches", response_model=list[str])
def list_branches(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[str]:
    require_member(project_id, db, user)
    with locked_repo(project_id) as repo:
        return repo.list_branches()


@router.post(
    "/{project_id}/branches", status_code=status.HTTP_201_CREATED, response_model=list[str]
)
def create_branch(
    project_id: int,
    payload: BranchIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[str]:
    require_member(project_id, db, user)
    try:
        with locked_repo(project_id) as repo:
            repo.create_branch(payload.name, payload.start_point)
            return repo.list_branches()
    except ProjectRepoError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post(
    "/{project_id}/commits",
    response_model=CommitResult,
    status_code=status.HTTP_201_CREATED,
)
def commit_l5x(
    project_id: int,
    branch: str = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> CommitResult:
    require_member(project_id, db, user)

    suffix = Path(file.filename or "upload.L5X").suffix or ".L5X"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    try:
        with locked_repo(project_id) as repo:
            info = repo.commit_l5x(
                tmp_path, branch=branch, title=title, description=description
            )
    except ProjectRepoError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    finally:
        os.unlink(tmp_path)
    return CommitResult(sha=info.sha, branch=info.branch, title=info.title)


@router.get("/{project_id}/commits", response_model=list[CommitOut])
def list_commits(
    project_id: int,
    branch: str = "main",
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[CommitOut]:
    require_member(project_id, db, user)
    with locked_repo(project_id) as repo:
        commits = repo.log(branch, limit=limit)
    return [
        CommitOut(
            sha=c.sha,
            title=c.title,
            description=c.description,
            author=c.author,
            date=c.date,
        )
        for c in commits
    ]


@router.get("/{project_id}/diff", response_model=ChangeSet)
def diff(
    project_id: int,
    base: str,
    head: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Semantic diff between two refs. Cached by the (base, head) commit pair."""
    require_member(project_id, db, user)
    return serve_diff(
        project_id, "changeset", base, head, lambda r, b, h: r.diff_refs(b, h)
    )


@router.get("/{project_id}/diff/ladder", response_model=LadderDocument)
def ladder_diff(
    project_id: int,
    base: str,
    head: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Drawable ladder-diagram diff between two refs (the visual view)."""
    require_member(project_id, db, user)
    return serve_diff(
        project_id,
        "ladder",
        base,
        head,
        lambda r, b, h: r.ladder_diff_refs(b, h, old_label=base, new_label=head),
    )
