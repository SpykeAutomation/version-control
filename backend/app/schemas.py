"""Request and response shapes for the API (separate from DB models)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr


# --- auth ---
class RegisterIn(BaseModel):
    email: EmailStr
    name: str
    password: str


class UserOut(BaseModel):
    id: int
    email: EmailStr
    name: str

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


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
    name: str
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
