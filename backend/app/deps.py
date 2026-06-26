"""Shared dependencies: membership/access checks for project routes.

Roles are per-project (a row in project_members):
- owner  — full control; cannot be removed or demoted here
- admin  — manage members, rename, settings, delete (a "manager")
- member — upload, comment, open/merge pull requests, view
"""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Project, ProjectMember, User

# Roles allowed to manage a project (members, rename, settings, delete).
MANAGER_ROLES = ("owner", "admin")


def _membership(
    project_id: int, db: Session, user: User
) -> tuple[Project, ProjectMember]:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    membership = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user.id,
        )
    )
    if membership is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this project")
    return project, membership


def require_member(project_id: int, db: Session, user: User) -> Project:
    """Any member may read and contribute (upload, comment, open/merge PRs)."""
    project, _ = _membership(project_id, db, user)
    return project


def require_manager(project_id: int, db: Session, user: User) -> Project:
    """Owner or admin: manage members, rename, change settings, delete."""
    project, membership = _membership(project_id, db, user)
    if membership.role not in MANAGER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Requires the owner or an admin")
    return project


def require_owner(project_id: int, db: Session, user: User) -> Project:
    """Owner only (e.g. removing or demoting an admin)."""
    project, membership = _membership(project_id, db, user)
    if membership.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Requires the project owner")
    return project


def membership_role(project_id: int, db: Session, user: User) -> str | None:
    """The caller's role on a project, or None if they are not a member."""
    return db.scalar(
        select(ProjectMember.role).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user.id,
        )
    )
