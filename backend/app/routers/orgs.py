"""Organization invitations: owners invite, recipients accept via a link.

Bootstrapping (creating an org + its owner) is an admin task done with
app.auth.create_org_with_owner. From there, only the owner can invite, and a
person joins only by accepting an invitation — never by naming an org.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from .. import audit
from ..auth import current_user, now_utc_naive
from ..db import get_db
from ..invites import (
    InviteError,
    accept_invitation,
    create_invitation,
    get_pending_invite,
)
from ..membership import transfer_project_ownership
from ..models import (
    DeviceAuthorization,
    Organization,
    Project,
    ProjectMember,
    User,
)
from ..ratelimit import client_ip, invite_rate_limit
from ..schemas import (
    AcceptIn,
    AcceptResult,
    InviteIn,
    InviteOut,
    InvitePreview,
    UserOut,
)

router = APIRouter(tags=["organizations"])


@router.get("/orgs/{org_id}/users", response_model=list[UserOut])
def list_org_users(
    org_id: int,
    response: Response,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[UserOut]:
    """Users in an organization (members + owner). Visible to anyone in that org.
    Indexed on organization_id, so it's fast; paginated via `limit`/`offset` with
    the total in the `X-Total-Count` header."""
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    if user.organization_id != org_id and org.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this organization")
    limit = max(1, min(limit, 200))
    total = db.scalar(
        select(func.count()).select_from(User).where(User.organization_id == org_id)
    )
    rows = db.scalars(
        select(User)
        .where(User.organization_id == org_id)
        .order_by(User.last_name, User.first_name, User.id)
        .limit(limit)
        .offset(max(0, offset))
    ).all()
    response.headers["X-Total-Count"] = str(total or 0)
    return [
        UserOut(
            id=u.id, email=u.email, first_name=u.first_name,
            last_name=u.last_name, organization=org.name, avatar=u.avatar,
        )
        for u in rows
    ]


def _require_owner(db: Session, org_id: int, user: User) -> Organization:
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    if org.owner_id != user.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the organization owner can do this"
        )
    return org


def _org_member(db: Session, org: Organization, user_id: int) -> User:
    """The target of an owner action: a real user currently in this org and not
    the owner themselves."""
    if user_id == org.owner_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Cannot act on the organization owner"
        )
    target = db.get(User, user_id)
    if target is None or target.organization_id != org.id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Not a member of this organization"
        )
    return target


@router.delete(
    "/orgs/{org_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_org_member(
    org_id: int,
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Owner-only: remove someone from the organization (un-map them). Their
    account and authored history stay; they're simply no longer in the org."""
    org = _require_owner(db, org_id, user)
    target = _org_member(db, org, user_id)
    target.organization_id = None
    audit.record(
        db,
        action="org.member.removed",
        actor_id=user.id,
        target_user_id=user_id,
        target_type="org_membership",
        target_id=org_id,
        summary=f"removed {target.email} from {org.name}",
        ip=client_ip(request),
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/orgs/{org_id}/accounts/{user_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_account(
    org_id: int,
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Owner-only: soft-delete a member's account. Cuts all access — login and
    every request rejected, org + project memberships removed, CLI sessions
    revoked — but keeps the user row so their commits, PRs, and comments remain
    (the frontend greys the name out via the `deleted` flag)."""
    org = _require_owner(db, org_id, user)
    target = _org_member(db, org, user_id)
    if target.deleted_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Account already deleted")

    target.deleted_at = now_utc_naive()
    target.organization_id = None
    # Reassign any projects they owned to the org owner, so nothing is orphaned.
    # (demote_previous_to=None: their memberships are dropped right below anyway.)
    owned = db.scalars(select(Project).where(Project.owner_id == user_id)).all()
    for project in owned:
        transfer_project_ownership(
            db, project=project, new_owner=user, demote_previous_to=None
        )
    # Drop their accesses (project memberships)…
    db.execute(delete(ProjectMember).where(ProjectMember.user_id == user_id))
    # …and revoke every live CLI session so their tokens stop working at once.
    db.execute(
        update(DeviceAuthorization)
        .where(
            DeviceAuthorization.user_id == user_id,
            DeviceAuthorization.status == "redeemed",
            DeviceAuthorization.revoked_at.is_(None),
        )
        .values(revoked_at=now_utc_naive())
    )
    audit.record(
        db,
        action="account.deleted",
        actor_id=user.id,
        target_user_id=user_id,
        target_type="account",
        target_id=user_id,
        summary=f"deleted account {target.email}",
        ip=client_ip(request),
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
