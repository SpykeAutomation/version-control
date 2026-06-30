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
    # Soft-delete: set when an org owner deletes the account. The row is kept so
    # the user's authored history (PRs, comments, commits) survives; access is
    # fully cut (login and every request rejected, memberships removed, CLI
    # sessions revoked) and the frontend greys the name out. Active = deleted_at
    # is None.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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


class DeviceAuthorization(Base):
    """A CLI device-login request (OAuth 2.0 Device Authorization Grant, RFC 8628).

    The raw device_code is never stored — only its SHA-256 hash, exactly like an
    invitation token. `user_code` is the short, human code the user approves in
    the web app while logged in. One-time: once a token is issued the row is
    marked 'redeemed'. Existing users only — `user_id` is set on approval and the
    flow never creates an account."""

    __tablename__ = "device_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending | approved | redeemed
    # The approving user; null until approved. CASCADE so a deleted user's
    # in-flight device requests go with them.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    # CLI-reported context, captured when the flow starts so the approval page can
    # show "approving a sign-in from <ip>/<client>" — the human's only defence
    # against a relayed or phished user_code. All nullable (headless/older clients
    # may send nothing); IP and user-agent are filled server-side, never trusted
    # from the client.
    client_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Once redeemed, this row doubles as the CLI *session* record. The CLI token
    # carries this row's id as `sid`; setting revoked_at cuts the session off
    # (current_user then rejects the token). last_used_at powers the "last active"
    # column in account settings — updated at most every few minutes, never on
    # every request.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


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


class AuditLog(Base):
    """Account- and security-level audit trail: CLI logins and revocations,
    member removals, account deletions.

    Distinct from Activity, which is the *per-project* feed (and requires a
    project_id). These events aren't tied to a single project, so they live here.
    `actor_id` and `target_user_id` are plain columns (not FKs) so the log
    survives the deletion of either party — like Activity.actor_id and
    Invitation.invited_by."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_actor_created", "actor_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # who acted
    action: Mapped[str] = mapped_column(String(50))  # e.g. "cli.approved", "account.deleted"
    target_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # affected user
    target_type: Mapped[str] = mapped_column(String(30), default="")  # cli_session|membership|account
    target_id: Mapped[str] = mapped_column(String(120), default="")
    summary: Mapped[str] = mapped_column(String(300), default="")  # human one-liner
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)  # actor's IP
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
