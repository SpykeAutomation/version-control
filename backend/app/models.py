"""Database models for the things Git does not store.

Commits, branches, and diffs live in each project's Git repo. The database
only holds accounts, project ownership/membership, pull requests, and the
discussion threads on them.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    # The user who owns/administers the org. Plain column (not a FK) to avoid a
    # circular foreign key with users.organization_id.
    owner_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(120))
    last_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    # A 3-character avatar code the frontend decodes into a fixed illustration
    # set (e.g. base / colour / accessory). No image is stored server-side.
    avatar: Mapped[str] = mapped_column(String(3), default="000")
    # A user may belong to one organization, or none (can/cannot be mapped).
    # SET NULL: deleting an org un-maps its users rather than deleting them.
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(
        String(20), default="member"
    )  # owner | admin | member


class BranchProtection(Base):
    """A protected branch. Git itself has no notion of protection, so the policy
    lives here: a row means "this branch is protected" (can't be deleted via the
    API) and carries how many approvals a PR into it needs before it can merge.
    The default branch is protected even without a row; a row may still exist for
    it to set `required_approvals`."""

    __tablename__ = "branch_protections"
    __table_args__ = (UniqueConstraint("project_id", "branch"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    branch: Mapped[str] = mapped_column(String(200))
    # Approvals a PR targeting this branch needs before it may merge (0 = none).
    required_approvals: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class PullRequest(Base):
    __tablename__ = "pull_requests"
    __table_args__ = (UniqueConstraint("project_id", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)  # human-facing PR # within a project
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    source_branch: Mapped[str] = mapped_column(String(200))
    target_branch: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|merged|closed
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    merge_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)


class PullReviewer(Base):
    """A user invited to review/approve a pull request."""

    __tablename__ = "pull_reviewers"
    __table_args__ = (UniqueConstraint("pull_request_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pull_request_id: Mapped[int] = mapped_column(
        ForeignKey("pull_requests.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class PullApproval(Base):
    """One user's review verdict on a pull request. At most one row per (PR,
    user); approving again just updates it. `state` is 'approved' or
    'changes_requested'. The count of 'approved' rows gates merging when the
    target branch requires approvals."""

    __tablename__ = "pull_approvals"
    __table_args__ = (UniqueConstraint("pull_request_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pull_request_id: Mapped[int] = mapped_column(
        ForeignKey("pull_requests.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    state: Mapped[str] = mapped_column(String(20))  # approved | changes_requested
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)


class Comment(Base):
    """A PR discussion comment. A top-level comment has `parent_id` null; a reply
    points at its parent (one level of threading). A *change-level* comment also
    carries an anchor — the file/routine/rung in a specific commit it's pinned
    to on the rendered diff; a plain PR-level comment leaves the anchor null."""

    __tablename__ = "comments"
    # The hot path fetches one PR's comments in creation order — index for it.
    __table_args__ = (Index("ix_comments_pr_created", "pull_request_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pull_request_id: Mapped[int] = mapped_column(
        ForeignKey("pull_requests.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE"), nullable=True, index=True
    )
    body: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    # Change-level anchor (all null for a plain PR-level comment).
    anchor_path: Mapped[str | None] = mapped_column(String(400), nullable=True)
    anchor_routine: Mapped[str | None] = mapped_column(String(200), nullable=True)
    anchor_rung: Mapped[int | None] = mapped_column(Integer, nullable=True)
    anchor_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Invitation(Base):
    """An owner's invitation for someone to join their organization.

    The raw token is never stored — only its SHA-256 hash. One-time use is
    enforced by `status`, time limit by `expires_at`.
    """

    __tablename__ = "invitations"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(20), default="member")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|accepted
    invited_by: Mapped[int] = mapped_column(Integer)  # references users.id
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    accepted_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Activity(Base):
    """One append-only event in a project's timeline (the activity feed / audit
    log): who did what to which target, when. Written in the same transaction as
    the action it records, so the feed never drifts from reality.

    `actor_id` is a plain column (not a FK) so the log survives the actor's
    deletion — like Organization.owner_id and Invitation.invited_by. `project_id`
    cascades, so deleting a project drops its feed. Reads are a single indexed
    query on (project_id, created_at)."""

    __tablename__ = "activities"
    __table_args__ = (Index("ix_activities_project_created", "project_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # users.id
    verb: Mapped[str] = mapped_column(String(50))  # e.g. "pull.merged", "comment.added"
    target_type: Mapped[str] = mapped_column(String(30), default="")  # pull|comment|branch|tag|commit
    target_id: Mapped[str] = mapped_column(String(120), default="")  # number/sha/name
    summary: Mapped[str] = mapped_column(String(300), default="")  # human one-liner
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
