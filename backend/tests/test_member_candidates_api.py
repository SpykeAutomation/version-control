"""API tests for GET /projects/{id}/member-candidates (the add-member search
box: same-org, non-member, non-deleted users only, owner/admin only) and the
same-org enforcement on POST /projects/{id}/members (unknown, deleted, and
other-org emails all get the same 404)."""
import os
import tempfile

# Point the app at a throwaway data dir BEFORE any app module is imported —
# app.config builds its settings singleton (SQLite path, repos dir) at import.
# When another API test module imported first, its data dir simply wins.
os.environ["PLCVC_DATA_DIR"] = tempfile.mkdtemp(prefix="plcvc-candidates-api-")

import pytest

# The engine-only environment (requirements-dev.txt) has no app stack; these
# API tests need it (requirements-app.txt). CI runs them in the api-tests job;
# the engine matrix skips this module instead of failing collection.
pytest.importorskip("fastapi", reason="API tests need requirements-app.txt")

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import create_org_with_owner, create_user, now_utc_naive
from app.db import SessionLocal
from app.main import app
from app.models import User

# Satisfies the password policy: >=12 chars with upper + lower + digit.
PW = "Abcdef123456"

OWNER = "olive.owner@spyke.example"
MEMBER = "mia.member@spyke.example"
ADMIN = "ava.admin@spyke.example"
DELETED = "dell.hood@spyke.example"
OUTSIDER = "jatinder.hoodwink@rival.example"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _login(client: TestClient, email: str) -> str:
    r = client.post("/auth/login", data={"username": email, "password": PW})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


class Seed:
    """Org "Spyke Search Co": owner Olive + colleagues Jatin Hooda, Jane
    Hoover, Bob Smith (candidates), Mia (project member), Ava (project admin),
    and soft-deleted Dell Hood. A second org holds Jatinder Hoodwink, who
    matches every fragment but must never surface."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        db = SessionLocal()
        try:
            org, _ = create_org_with_owner(
                db, name="Spyke Search Co", owner_email=OWNER,
                owner_first="Olive", owner_last="Owner", owner_password=PW,
            )
            rival, _ = create_org_with_owner(
                db, name="Rival Robotics", owner_email="rita@rival.example",
                owner_first="Rita", owner_last="Rival", owner_password=PW,
            )
            colleagues = [
                ("jatin.hooda@spyke.example", "Jatin", "Hooda"),
                ("jane.hoover@spyke.example", "Jane", "Hoover"),
                ("bob.smith@spyke.example", "Bob", "Smith"),
                (MEMBER, "Mia", "Member"),
                (ADMIN, "Ava", "Admin"),
            ]
            for email, first, last in colleagues:
                create_user(
                    db, email=email, first_name=first, last_name=last,
                    password=PW, organization_id=org.id,
                )
            dell = create_user(
                db, email=DELETED, first_name="Dell", last_name="Hood",
                password=PW, organization_id=org.id,
            )
            dell.deleted_at = now_utc_naive()
            create_user(
                db, email=OUTSIDER, first_name="Jatinder", last_name="Hoodwink",
                password=PW, organization_id=rival.id,
            )
            db.commit()
        finally:
            db.close()

        self.owner = _login(client, OWNER)
        self.member = _login(client, MEMBER)
        self.admin = _login(client, ADMIN)
        self.pid = client.post(
            "/projects", json={"name": "Search Demo"}, headers=_auth(self.owner)
        ).json()["id"]
        for email, role in ((MEMBER, "member"), (ADMIN, "admin")):
            r = client.post(
                f"/projects/{self.pid}/members",
                json={"email": email, "role": role},
                headers=_auth(self.owner),
            )
            assert r.status_code == 201, r.text  # same-org adds still work

    def search(self, token: str, q: str):
        return self.client.get(
            f"/projects/{self.pid}/member-candidates",
            params={"q": q},
            headers=_auth(token),
        )


@pytest.fixture(scope="module")
def seed(client: TestClient) -> Seed:
    return Seed(client)


def _emails(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [row["email"] for row in response.json()]


# --- the search ---------------------------------------------------------------


def test_finds_by_name_fragment_case_insensitive(client, seed):
    r = seed.search(seed.owner, "HOO")
    # Hooda and Hoover match; deleted Dell Hood and other-org Hoodwink do not.
    assert _emails(r) == ["jatin.hooda@spyke.example", "jane.hoover@spyke.example"]
    brief = r.json()[0]
    assert set(brief) == {"id", "email", "first_name", "last_name", "avatar"}


def test_finds_by_email_fragment(client, seed):
    r = seed.search(seed.owner, "spyke.example")
    # Every active, same-org non-member — not Olive/Mia/Ava (members), not Dell.
    assert _emails(r) == [
        "jatin.hooda@spyke.example",
        "jane.hoover@spyke.example",
        "bob.smith@spyke.example",
    ]


def test_excludes_existing_members(client, seed):
    assert _emails(seed.search(seed.owner, "mia")) == []
    assert _emails(seed.search(seed.owner, "ava")) == []


def test_excludes_other_org_and_deleted_users(client, seed):
    # "jat" matches Jatin (in org) and Jatinder (other org): only Jatin shows.
    assert _emails(seed.search(seed.owner, "jat")) == ["jatin.hooda@spyke.example"]
    assert _emails(seed.search(seed.owner, "dell")) == []


def test_short_query_returns_empty(client, seed):
    assert _emails(seed.search(seed.owner, "j")) == []
    assert _emails(seed.search(seed.owner, "  ")) == []


def test_like_wildcards_match_literally(client, seed):
    assert _emails(seed.search(seed.owner, "%%")) == []
    assert _emails(seed.search(seed.owner, "__")) == []


def test_results_cap_at_ten(client, seed):
    db = SessionLocal()
    try:
        org_id = db.scalar(
            select(User.organization_id).where(User.email == OWNER)
        )
        for i in range(1, 13):
            create_user(
                db, email=f"zed{i:02d}@spyke.example", first_name="Zed",
                last_name=f"Query{i:02d}", password=PW, organization_id=org_id,
            )
        db.commit()
    finally:
        db.close()
    rows = seed.search(seed.owner, "query").json()
    assert [r["last_name"] for r in rows] == [f"Query{i:02d}" for i in range(1, 11)]


# --- access control -----------------------------------------------------------


def test_plain_member_gets_403(client, seed):
    assert seed.search(seed.member, "hoo").status_code == 403


def test_unauthenticated_gets_401(client, seed):
    r = client.get(f"/projects/{seed.pid}/member-candidates", params={"q": "hoo"})
    assert r.status_code == 401


# --- same-org enforcement on the add itself ------------------------------------


def test_add_rejects_other_org_deleted_and_unknown_alike(client, seed):
    for email in (OUTSIDER, DELETED, "nobody@nowhere.example"):
        r = client.post(
            f"/projects/{seed.pid}/members",
            json={"email": email},
            headers=_auth(seed.owner),
        )
        assert r.status_code == 404, (email, r.text)
        assert r.json()["detail"] == "No registered user with that email"


# --- same-org enforcement on ownership transfer --------------------------------


def test_transfer_rejects_other_org_user(client, seed):
    pid = client.post(
        "/projects", json={"name": "Transfer Demo"}, headers=_auth(seed.owner)
    ).json()["id"]
    db = SessionLocal()
    try:
        outsider_id = db.scalar(select(User.id).where(User.email == OUTSIDER))
        colleague_id = db.scalar(
            select(User.id).where(User.email == "jatin.hooda@spyke.example")
        )
    finally:
        db.close()
    r = client.post(
        f"/projects/{pid}/transfer",
        json={"new_owner_id": outsider_id},
        headers=_auth(seed.owner),
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "User not found"  # same answer as a bogus id
    # A same-org colleague works and lands as owner.
    r = client.post(
        f"/projects/{pid}/transfer",
        json={"new_owner_id": colleague_id},
        headers=_auth(seed.owner),
    )
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "owner"


# --- rate limit (last: it fills the admin account's budget) --------------------


def test_search_is_rate_limited_per_account(client, seed):
    for _ in range(30):
        assert seed.search(seed.admin, "hoo").status_code == 200
    r = seed.search(seed.admin, "hoo")
    assert r.status_code == 429
    assert "Retry-After" in r.headers
    # The owner's budget is untouched — the limit is per account, not per IP.
    assert seed.search(seed.owner, "hoo").status_code == 200
