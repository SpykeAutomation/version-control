"""Organization invitations: owners invite, recipients accept via a link.

Bootstrapping (creating an org + its owner) is an admin task done with
app.auth.create_org_with_owner. From there, only the owner can invite, and a
person joins only by accepting an invitation — never by naming an org.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..invites import (
    InviteError,
    accept_invitation,
    create_invitation,
    get_pending_invite,
)
from ..models import Organization, User
from ..ratelimit import invite_rate_limit
from ..schemas import AcceptIn, AcceptResult, InviteIn, InviteOut, InvitePreview

router = APIRouter(tags=["organizations"])


def _require_owner(db: Session, org_id: int, user: User) -> Organization:
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    if org.owner_id != user.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the organization owner can do this"
        )
    return org


@router.post(
    "/orgs/{org_id}/invites",
    response_model=InviteOut,
    status_code=status.HTTP_201_CREATED,
)
def create_invite(
    org_id: int,
    payload: InviteIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> InviteOut:
    """Owner-only: invite someone by email. Returns a one-time link to share."""
    org = _require_owner(db, org_id, user)
    token, invite = create_invitation(
        db, organization=org, email=payload.email, role=payload.role, invited_by=user
    )
    return InviteOut(
        email=invite.email,
        role=invite.role,
        organization=org.name,
        status=invite.status,
        expires_at=invite.expires_at,
        token=token,
        accept_path=f"/invites/{token}/accept",
    )


@router.get("/invites/{token}", response_model=InvitePreview)
def preview_invite(
    token: str,
    db: Session = Depends(get_db),
    _: None = Depends(invite_rate_limit),
) -> InvitePreview:
    """Public: show what this invitation is for (so the accept page can render)."""
    try:
        invite = get_pending_invite(db, token)
    except InviteError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    org = db.get(Organization, invite.organization_id)
    return InvitePreview(
        organization=org.name if org else "",
        email=invite.email,
        role=invite.role,
        status=invite.status,
    )


@router.post("/invites/{token}/accept", response_model=AcceptResult)
def accept_invite(
    token: str,
    payload: AcceptIn,
    db: Session = Depends(get_db),
    _: None = Depends(invite_rate_limit),
) -> AcceptResult:
    """Public: accept by confirming the invited email. New users also set a
    password + name (account created); existing users are just linked."""
    try:
        _user, issued = accept_invitation(
            db,
            token=token,
            email=payload.email,
            first_name=payload.first_name,
            last_name=payload.last_name,
            password=payload.password,
        )
    except InviteError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    except ValueError as exc:  # e.g. weak password from create_user
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    return AcceptResult(status="accepted", access_token=issued)
