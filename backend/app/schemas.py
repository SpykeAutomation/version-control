"""Request and response shapes for the API (separate from DB models)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, EmailStr

from diff import RoutineLadderDiff


# --- auth ---
class UserOut(BaseModel):
    id: int
    email: EmailStr
    first_name: str
    last_name: str
    organization: Optional[str] = None
    avatar: str = "000"  # 3-char code; the frontend renders the illustration
    deleted: bool = False  # soft-deleted account; the frontend greys it out


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ProfileUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    avatar: Optional[str] = None  # exactly 3 chars from the fixed alphabet


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


# --- device authorization (CLI login, RFC 8628) ---
class DeviceCodeIn(BaseModel):
    # Optional client self-description shown to the user at approval time, e.g.
    # "spyke-cli/0.3.0 (macOS 14)". The IP and user-agent are captured
    # server-side; only this label comes from the CLI.
    client_name: Optional[str] = None


class DeviceCodeOut(BaseModel):
    device_code: str  # the CLI polls with this; the server stores only its hash
    user_code: str  # short code the user confirms in the browser
    verification_uri: str  # where to approve (the web app's /cli-auth page)
    verification_uri_complete: str  # the same URL with ?code= prefilled
    interval: int  # seconds the CLI should wait between token polls
    expires_in: int  # seconds until both codes expire


class DeviceInfoOut(BaseModel):
    # Context the /cli-auth page shows before the user approves, so they can spot
    # a relayed sign-in ("you're approving a login from somewhere you don't
    # recognise"). Read-only lookup of a still-pending request.
    user_code: str
    client_name: Optional[str] = None
    client_ip: Optional[str] = None
    requested_at: datetime
    expires_in: int  # seconds until the request expires


class DeviceApproveIn(BaseModel):
    user_code: str


class DeviceApproveResult(BaseModel):
    status: str = "approved"


class CliSessionOut(BaseModel):
    # One authorized CLI login, shown in account settings with a revoke button.
    id: int
    client_name: Optional[str] = None
    client_ip: Optional[str] = None
    created_at: datetime  # when the CLI logged in (the approval was redeemed)
    last_used_at: Optional[datetime] = None
    expires_at: datetime  # hard expiry: login time + the CLI token lifetime
    current: bool = False  # the session making this request


class DeviceTokenIn(BaseModel):
    device_code: str


# --- organizations & invitations ---
class InviteIn(BaseModel):
    email: EmailStr
    role: str = "member"


class InviteOut(BaseModel):
    email: EmailStr
    role: str
    organization: str
    status: str
    expires_at: datetime
    token: str  # raw token, shown once; put it in the link you share
    accept_path: str


class InvitePreview(BaseModel):
    organization: str
    email: EmailStr
    role: str
    status: str


class AcceptIn(BaseModel):
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    password: Optional[str] = None  # required only for a brand-new account


class AcceptResult(BaseModel):
    status: str
    access_token: Optional[str] = None  # set only when a new account was created


# --- projects ---
class ProjectIn(BaseModel):
    name: str
    description: str = ""


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class ProjectOut(BaseModel):
    id: int
    name: str
    slug: str
    description: str = ""
    owner: UserOut
    your_role: Optional[str] = None  # the requesting user's role on this project
    created_at: datetime
    branches: list[str] = []


class MemberIn(BaseModel):
    email: EmailStr
    role: str = "member"


class RoleUpdate(BaseModel):
    role: str  # "admin" | "member"


class TransferIn(BaseModel):
    new_owner_id: int  # the user to hand project ownership to


class MemberOut(BaseModel):
    id: int
    email: EmailStr
    first_name: str
    last_name: str
    role: str


class BranchIn(BaseModel):
    name: str
    start_point: str = "main"


class CommitOut(BaseModel):
    sha: str
    title: str
    description: str = ""
    author: str = ""
    date: str = ""
    branch: Optional[str] = None  # the branch this was listed under (when known)
    files_changed: int = 0  # logical files changed vs the first parent


class CommitResult(BaseModel):
    sha: str
    branch: str
    title: str


class RevertIn(BaseModel):
    """POST /projects/{id}/revert — restore `target_sha`'s repo state as ONE
    new commit on top of the branch's current tip (history is preserved).
    `expected_tip_sha` is the tip the client previewed against: if the branch
    has moved since, the revert is rejected with 409 instead of silently
    stacking onto commits the user never saw."""

    branch: str
    target_sha: str
    expected_tip_sha: str
    message: Optional[str] = None  # commit title; a default is built if omitted
    description: Optional[str] = None  # optional longer body (the "why")


# --- branches ---
class BranchOut(BaseModel):
    name: str
    is_default: bool = False  # the repo's default branch ("main")
    is_protected: bool = False  # default branch, or explicitly protected
    required_approvals: int = 0  # approvals a PR into this branch needs to merge
    latest_commit: Optional[CommitOut] = None  # None on an unborn branch
    ahead: int = 0  # commits on this branch not on the default branch
    behind: int = 0  # commits on the default branch not on this one
    merged: bool = False  # fully merged into the default branch (ahead == 0)


class BranchProtectionIn(BaseModel):
    protected: bool
    required_approvals: int = 0  # ignored when protected is false


# --- tags / releases ---
class TagIn(BaseModel):
    name: str
    ref: str = "main"  # the commit/branch/ref to tag
    message: str = ""  # release notes; a non-empty message makes an annotated tag


class TagOut(BaseModel):
    name: str
    sha: str  # the commit the tag points to
    message: str = ""  # release notes (empty for a lightweight tag)
    tagger: str = ""  # who cut the tag (or the target commit's committer)
    date: str = ""  # ISO-8601 tag date (annotated) or commit date (lightweight)
    annotated: bool = False
    commit: Optional[CommitOut] = None  # the tagged commit's summary


# --- repository overview & storage ---
class RepositoryOverview(BaseModel):
    id: int
    name: str
    description: str = ""
    default_branch: str = "main"
    file_count: int
    l5x_count: int
    open_pull_count: int
    unresolved_comment_count: int
    controller_name: Optional[str] = None
    processor_type: Optional[str] = None  # the controller "model", e.g. 1756-L83E
    firmware: Optional[str] = None  # "major.minor"
    latest_commit: Optional[CommitOut] = None
    latest_release: Optional[TagOut] = None  # newest tag, for the "Latest release" card


class StorageUsage(BaseModel):
    used_bytes: int
    limit_bytes: int
    project_count: int


# --- multi-file project contents & diffs ---
class FileEntry(BaseModel):
    path: str  # "l5x/<name>" or "files/<nested/path>"
    kind: Literal["l5x", "file"]
    size: int = 0  # bytes (for an L5X file, its original source.L5X size)
    modified_by: str = ""  # author of the last commit that touched it
    modified_at: str = ""  # ISO-8601 timestamp of that commit


class FileListing(BaseModel):
    files: list[FileEntry] = []


class ChangedFile(BaseModel):
    path: str
    kind: Literal["l5x", "file"]
    change: Literal["added", "modified", "removed"]
    # Drill-down diff views that apply to this file: l5x -> changeset+ladder,
    # other files -> text (which itself reports binary files as having no diff).
    views: list[str] = []


class DiffManifest(BaseModel):
    files: list[ChangedFile] = []


class CommitDetail(BaseModel):
    """One commit plus the files it changed vs its first parent (the root commit
    diffs against the empty tree, so everything shows as added)."""

    sha: str
    title: str
    description: str = ""
    author: str = ""
    date: str = ""
    branch: Optional[str] = None
    parent: Optional[str] = None  # first-parent SHA; None for the root commit
    files_changed: int = 0
    files: list[ChangedFile] = []  # same manifest shape as /diff


class TextDiff(BaseModel):
    path: str
    binary: bool
    unified: Optional[str] = None  # None for binary files (no line diff)


# --- full routine content at a commit (not a diff) ---
class RoutineLine(BaseModel):
    ln: int  # 1-based line number
    text: str


class RoutineFullCode(BaseModel):
    """A structured-text routine's full content as of one commit."""

    kind: Literal["structured"] = "structured"
    ref: str  # short commit label, e.g. "a7f3c9d"
    lines: list[RoutineLine] = []


class RoutineFullLadder(BaseModel):
    """A ladder routine's full content as of one commit, in the ladder-diff IR
    (every rung "unchanged" with only the `after` side filled) so the frontend
    reuses its LadderDiff renderer single-column."""

    kind: Literal["ladder"] = "ladder"
    ladder: RoutineLadderDiff


class L5XSection(BaseModel):
    """Envelope for GET /projects/{id}/l5x — one section of a parsed L5X file
    at a ref. `data` is serialized straight from the parser models (see
    backend/README.md for the per-section shape and the heavy per-entity
    fields each list section excludes)."""

    schema_version: int = 1
    section: str
    data: Any = None


# --- pull requests ---
class PullIn(BaseModel):
    title: str
    description: str = ""  # optional human summary, editable later
    source_branch: str
    target_branch: str = "main"


class PullUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None


class ReviewerIn(BaseModel):
    email: EmailStr


class ReviewOut(BaseModel):
    user: UserOut
    state: Literal["approved", "changes_requested"]
    created_at: datetime


class PullOut(BaseModel):
    number: int
    title: str
    description: str
    source_branch: str
    target_branch: str
    status: str
    author: UserOut
    merge_sha: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    reviewers: list[UserOut] = []  # invited approvers
    reviews: list[ReviewOut] = []  # verdicts cast so far
    required_approvals: int = 0  # from the target branch's protection
    approvals: int = 0  # count of 'approved' verdicts
    approved: bool = False  # approvals >= required_approvals


class MergeabilityOut(BaseModel):
    mergeable: bool  # no merge conflicts (dry run)
    conflicts: list[str] = []  # files that would conflict
    approvals: int = 0
    required_approvals: int = 0
    approved: bool = False
    can_merge: bool = False  # open + mergeable + approved


class MergeResult(BaseModel):
    status: Literal["merged", "conflict"]
    message: str
    merge_sha: Optional[str] = None
    conflicts: list[str] = []


# --- comments ---
class CommentAnchor(BaseModel):
    """Where a change-level comment is pinned on the rendered diff (the frontend
    supplies these from the location the user clicked). All omitted = PR-level."""

    path: Optional[str] = None  # "l5x/<name>" or "files/<path>"
    routine: Optional[str] = None  # routine name within an L5X file
    rung: Optional[int] = None  # rung number on the head side
    sha: Optional[str] = None  # the commit the comment was made against


class CommentIn(BaseModel):
    body: str
    parent_id: Optional[int] = None  # set to reply to another comment
    anchor: Optional[CommentAnchor] = None


class CommentUpdate(BaseModel):
    body: Optional[str] = None  # author only
    resolved: Optional[bool] = None  # any member


class CommentOut(BaseModel):
    id: int
    author: UserOut
    body: str
    resolved: bool = False
    parent_id: Optional[int] = None
    anchor: Optional[CommentAnchor] = None
    created_at: datetime
    edited_at: Optional[datetime] = None


# --- compare (ref-to-ref view model) ---
class CompareSummary(BaseModel):
    commits: int = 0  # commits on head not on base
    files_changed: int = 0
    l5x_changed: int = 0
    rungs_added: int = 0
    rungs_removed: int = 0
    rungs_modified: int = 0
    routines_modified: int = 0
    tags_impacted: int = 0


class CompareRow(BaseModel):
    """One changed file with a rolled-up impact (for the Compare table)."""

    path: str
    kind: Literal["l5x", "file"]
    change: Literal["added", "modified", "removed"]
    rungs_added: int = 0
    rungs_removed: int = 0
    rungs_modified: int = 0
    symbols: list[str] = []  # affected tags/routines/UDTs/AOIs in this file
    views: list[str] = []  # drill-down views, same as a manifest entry


class CompareView(BaseModel):
    base: str
    head: str
    summary: CompareSummary
    files: list[CompareRow] = []
    affected_symbols: list[str] = []  # de-duplicated across all files


# --- activity feed / audit log ---
class ActivityOut(BaseModel):
    id: int
    actor: Optional[UserOut] = None  # null if the actor was since deleted
    verb: str  # e.g. "pull.merged", "comment.added", "branch.created"
    target_type: str = ""
    target_id: str = ""
    summary: str = ""
    created_at: datetime
