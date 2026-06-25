"""Request and response shapes for the API (separate from DB models)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr


# --- auth ---
class UserOut(BaseModel):
    id: int
    email: EmailStr
    first_name: str
    last_name: str
    organization: Optional[str] = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


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


class ProjectOut(BaseModel):
    id: int
    name: str
    slug: str
    owner_id: int
    created_at: datetime
    branches: list[str] = []

    model_config = {"from_attributes": True}


class MemberIn(BaseModel):
    email: EmailStr
    role: str = "member"


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


class CommitResult(BaseModel):
    sha: str
    branch: str
    title: str


# --- pull requests ---
class PullIn(BaseModel):
    title: str
    description: str = ""
    source_branch: str
    target_branch: str = "main"


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


class MergeResult(BaseModel):
    status: Literal["merged", "conflict"]
    message: str
    merge_sha: Optional[str] = None
    conflicts: list[str] = []


# --- comments ---
class CommentIn(BaseModel):
    body: str


class CommentOut(BaseModel):
    id: int
    author: UserOut
    body: str
    created_at: datetime
