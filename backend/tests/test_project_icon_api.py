"""API tests for the per-project repository icon: an integer code 0..19,
stored on create (server-random when omitted, so every project has one),
changeable by owner/admin via PATCH, echoed on every Project payload."""
import os
import tempfile

# Point the app at a throwaway data dir BEFORE any app module is imported —
# app.config builds its settings singleton (SQLite path, repos dir) at import.
# When another API test module imported first, its data dir simply wins.
os.environ["PLCVC_DATA_DIR"] = tempfile.mkdtemp(prefix="plcvc-icon-api-")

import pytest

# The engine-only environment (requirements-dev.txt) has no app stack; these
# API tests need it (requirements-app.txt). CI runs them in the api-tests job;
# the engine matrix skips this module instead of failing collection.
pytest.importorskip("fastapi", reason="API tests need requirements-app.txt")

from fastapi.testclient import TestClient

from app.auth import create_user
from app.db import SessionLocal
from app.main import app

# Satisfies the password policy: >=12 chars with upper + lower + digit.
PW = "Abcdef123456"

OWNER = "icon-owner@example.com"
ADMIN = "icon-admin@example.com"
MEMBER = "icon-member@example.com"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _login(client: TestClient, email: str, first: str, last: str) -> str:
    db = SessionLocal()
    try:
        create_user(db, email=email, first_name=first, last_name=last, password=PW)
    finally:
        db.close()
    r = client.post("/auth/login", data={"username": email, "password": PW})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


class Seed:
    """One project created WITH an explicit icon, plus an admin and a plain
    member on it (for the PATCH gate tests)."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.owner = _login(client, OWNER, "Iva", "Owner")
        self.admin = _login(client, ADMIN, "Ian", "Admin")
        self.member = _login(client, MEMBER, "Imo", "Member")
        r = client.post(
            "/projects", json={"name": "Icon Demo", "icon": 5}, headers=_auth(self.owner)
        )
        assert r.status_code == 201, r.text
        self.created = r.json()
        self.pid = self.created["id"]
        for email, role in ((ADMIN, "admin"), (MEMBER, "member")):
            r = client.post(
                f"/projects/{self.pid}/members",
                json={"email": email, "role": role},
                headers=_auth(self.owner),
            )
            assert r.status_code == 201, r.text

    def patch_icon(self, token: str, icon):
        return self.client.patch(
            f"/projects/{self.pid}", json={"icon": icon}, headers=_auth(token)
        )


@pytest.fixture(scope="module")
def seed(client: TestClient) -> Seed:
    return Seed(client)


def test_create_with_icon_echoes_it(client, seed):
    assert seed.created["icon"] == 5


def test_create_without_icon_stores_a_random_valid_one(client, seed):
    r = client.post(
        "/projects", json={"name": "No Icon Given"}, headers=_auth(seed.owner)
    )
    assert r.status_code == 201, r.text
    icon = r.json()["icon"]
    assert isinstance(icon, int) and 0 <= icon <= 19


def test_create_with_out_of_range_icon_400s(client, seed):
    for bad in (-1, 20, 999):
        r = client.post(
            "/projects", json={"name": "Bad", "icon": bad}, headers=_auth(seed.owner)
        )
        assert r.status_code == 400, (bad, r.text)
    # A non-integer fails the schema itself (FastAPI validation).
    r = client.post(
        "/projects", json={"name": "Bad", "icon": "sparkles"}, headers=_auth(seed.owner)
    )
    assert r.status_code == 422


def test_admin_can_change_icon_and_response_echoes(client, seed):
    r = seed.patch_icon(seed.admin, 7)
    assert r.status_code == 200, r.text
    assert r.json()["icon"] == 7  # the frontend's success detection reads this
    # Picker glyph ids start at 0 — the first glyph must be storable.
    r = seed.patch_icon(seed.admin, 0)
    assert r.status_code == 200
    assert r.json()["icon"] == 0


def test_plain_member_cannot_change_icon(client, seed):
    assert seed.patch_icon(seed.member, 3).status_code == 403


def test_patch_out_of_range_icon_400s_and_changes_nothing(client, seed):
    assert seed.patch_icon(seed.owner, 20).status_code == 400
    r = client.get(f"/projects/{seed.pid}", headers=_auth(seed.owner))
    assert r.json()["icon"] == 0  # still the last accepted value


def test_list_and_detail_echo_the_icon(client, seed):
    rows = client.get("/projects", headers=_auth(seed.owner)).json()
    by_id = {p["id"]: p for p in rows}
    assert by_id[seed.pid]["icon"] == 0
    detail = client.get(f"/projects/{seed.pid}", headers=_auth(seed.owner)).json()
    assert detail["icon"] == 0
