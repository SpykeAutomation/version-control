"""Project-membership mutations shared across routers.

Lives outside the routers so both projects (manual ownership transfer) and orgs
(auto-reassign when an owning account is deleted) can call it without importing
one router from another. Mutations are staged; the caller commits.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Project, ProjectMember, User


def transfer_project_ownership(
    db: Session,
    *,
    project: Project,
    new_owner: User,
    demote_previous_to: str | None = "admin",
) -> None:
    """Hand a project to ``new_owner``: repoint ``Project.owner_id`` and give them
    an ``owner`` membership row (created if missing, upgraded if present).

    The previous owner's membership is set to ``demote_previous_to`` (default
    ``admin`` so they keep access on a manual hand-off). Pass ``None`` to leave it
    untouched — used by account deletion, which removes the old owner's
    memberships immediately afterwards anyway.
    """
    previous_owner_id = project.owner_id
    project.owner_id = new_owner.id

    new_membership = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == new_owner.id,
        )
    )
    if new_membership is None:
        db.add(
            ProjectMember(project_id=project.id, user_id=new_owner.id, role="owner")
        )
    else:
        new_membership.role = "owner"

    if demote_previous_to is not None and previous_owner_id != new_owner.id:
        previous = db.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == previous_owner_id,
            )
        )
        if previous is not None:
            previous.role = demote_previous_to
