"""API tests for the configurable per-project default branch: owner-only
PATCH /projects/{id} {default_branch}, validation, and every place the stored
default replaces the old hardcoded "main" (is_default + ahead/behind base,
deletion guard, implicit protection incl. the owner-only unprotect, branch
start_point, PR target, and the ?branch=/?ref= fallbacks)."""
import os
import tempfile

# Point the app at a throwaway data dir BEFORE any app module is imported —
# app.config builds its settings singleton (SQLite path, repos dir) at import.
# When another API test module imported first, its data dir simply wins.
os.environ["PLCVC_DATA_DIR"] = tempfile.mkdtemp(prefix="plcvc-default-branch-")

import pytest

# The engine-only environment (requirements-dev.txt) has no app stack; these
# API tests need it (requirements-app.txt). CI runs them in the api-tests job;
# the engine matrix skips this module instead of failing collection.
pytest.importorskip("fastapi", reason="API tests need requirements-app.txt")

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import create_user
from app.db import SessionLocal
from app.main import app
from app.models import AuditLog

# Satisfies the password policy: >=12 chars with upper + lower + digit.
PW = "Abcdef123456"

OWNER = "defbranch-owner@example.com"
ADMIN = "defbranch-admin@example.com"


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
    """main: one commit A. develop: off main + commit B (ahead 1). feature-x:
    off main + commit C. Owner + a project admin. Tests then flip the default
    to develop and check every consumer of the stored value, in order."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.owner = _login(client, OWNER, "Odette", "Owner")
        self.admin = _login(client, ADMIN, "Andy", "Admin")
        self.pid = client.post(
            "/projects", json={"name": "Default Branch Demo"}, headers=_auth(self.owner)
        ).json()["id"]
        r = client.post(
            f"/projects/{self.pid}/members",
            json={"email": ADMIN, "role": "admin"},
            headers=_auth(self.owner),
        )
        assert r.status_code == 201, r.text
        self.commit("main", "A: seed main")
        for name in ("develop", "feature-x"):
            r = client.post(
                f"/projects/{self.pid}/branches",
                json={"name": name, "start_point": "main"},
                headers=_auth(self.owner),
            )
            assert r.status_code == 201, r.text
        self.commit("develop", "B: develop work")
        self.commit("feature-x", "C: feature work")

    def commit(self, branch: str, title: str) -> str:
        r = self.client.post(
            f"/projects/{self.pid}/commits",
            files=[("files", (f"{title[0]}.txt", title, "application/octet-stream"))],
            data={"branch": branch, "title": title},
            headers=_auth(self.owner),
        )
        assert r.status_code == 201, r.text
        return r.json()["sha"]

    def patch(self, token: str, **payload):
        return self.client.patch(
            f"/projects/{self.pid}", json=payload, headers=_auth(token)
        )

    def branches(self) -> dict[str, dict]:
        r = self.client.get(
            f"/projects/{self.pid}/branches", headers=_auth(self.owner)
        )
        assert r.status_code == 200, r.text
        return {b["name"]: b for b in r.json()}

    def protect(self, token: str, branch: str, protected: bool):
        return self.client.put(
            f"/projects/{self.pid}/branches/{branch}/protection",
            json={"protected": protected},
            headers=_auth(token),
        )


@pytest.fixture(scope="module")
def seed(client: TestClient) -> Seed:
    return Seed(client)


# The tests run in order and share the seed's state: the default is flipped to
# `develop` in test_owner_changes_default and stays that way afterwards.


def test_admin_cannot_change_default_but_can_still_edit(client, seed):
    assert seed.patch(seed.admin, default_branch="develop").status_code == 403
    r = seed.patch(seed.admin, description="edited by admin")
    assert r.status_code == 200
    assert r.json()["default_branch"] == "main"  # unchanged by the 403 above


def test_unknown_branch_is_400(client, seed):
    r = seed.patch(seed.owner, default_branch="ghost")
    assert r.status_code == 400
    assert "ghost" in r.json()["detail"]


def test_same_value_is_a_noop(client, seed):
    r = seed.patch(seed.owner, default_branch="main")
    assert r.status_code == 200
    assert r.json()["default_branch"] == "main"


def test_owner_changes_default(client, seed):
    # An explicit protection row on the soon-to-be-old default must survive.
    assert seed.protect(seed.owner, "main", True).status_code == 200

    r = seed.patch(seed.owner, default_branch="develop")
    assert r.status_code == 200, r.text
    assert r.json()["default_branch"] == "develop"

    views = seed.branches()
    assert views["develop"]["is_default"] is True
    assert views["develop"]["is_protected"] is True  # implicit, no row needed
    assert views["main"]["is_default"] is False
    assert views["main"]["is_protected"] is True  # explicit row survived
    # ahead/behind is now measured against develop: main has nothing develop
    # lacks (merged) and is one commit behind it.
    assert (views["main"]["ahead"], views["main"]["behind"]) == (0, 1)
    assert views["main"]["merged"] is True
    # feature-x has its own commit and lacks develop's.
    assert (views["feature-x"]["ahead"], views["feature-x"]["behind"]) == (1, 1)

    # The change is audited old -> new.
    db = SessionLocal()
    try:
        entry = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "project.default_branch.changed",
                AuditLog.target_id == str(seed.pid),
            )
        )
    finally:
        db.close()
    assert entry is not None
    assert "main -> develop" in entry.summary


def test_fallbacks_follow_the_new_default(client, seed):
    overview = client.get(
        f"/projects/{seed.pid}/overview", headers=_auth(seed.owner)
    ).json()
    assert overview["default_branch"] == "develop"
    assert overview["latest_commit"]["title"] == "B: develop work"

    commits = client.get(
        f"/projects/{seed.pid}/commits", headers=_auth(seed.owner)
    )
    assert commits.headers["X-Total-Count"] == "2"  # develop: A + B
    assert commits.json()[0]["title"] == "B: develop work"

    files = client.get(
        f"/projects/{seed.pid}/files", headers=_auth(seed.owner)
    ).json()["files"]
    assert {f["path"] for f in files} == {"files/A.txt", "files/B.txt"}


def test_pull_without_target_lands_on_new_default(client, seed):
    r = client.post(
        f"/projects/{seed.pid}/pulls",
        json={"title": "Feature X", "source_branch": "feature-x"},
        headers=_auth(seed.owner),
    )
    assert r.status_code == 201, r.text
    assert r.json()["target_branch"] == "develop"


def test_branch_creation_starts_from_new_default(client, seed):
    r = client.post(
        f"/projects/{seed.pid}/branches",
        json={"name": "hotfix"},
        headers=_auth(seed.owner),
    )
    assert r.status_code == 201, r.text
    views = seed.branches()
    assert (
        views["hotfix"]["latest_commit"]["sha"]
        == views["develop"]["latest_commit"]["sha"]
    )


def test_new_default_cannot_be_deleted_or_admin_unprotected(client, seed):
    r = client.delete(
        f"/projects/{seed.pid}/branches/develop", headers=_auth(seed.owner)
    )
    assert r.status_code == 400
    assert "default" in r.json()["detail"].lower()
    # Unprotecting the *current* default is the owner's call alone.
    assert seed.protect(seed.admin, "develop", False).status_code == 403


def test_old_default_relaxes_and_can_be_deleted(client, seed):
    # Still explicitly protected -> deletion blocked for that reason.
    r = client.delete(
        f"/projects/{seed.pid}/branches/main", headers=_auth(seed.owner)
    )
    assert r.status_code == 400
    assert "protected" in r.json()["detail"].lower()
    # main is no longer the default, so an ADMIN may now unprotect it (the
    # owner-only rule follows the stored default, not the name "main").
    assert seed.protect(seed.admin, "main", False).status_code == 200
    r = client.delete(
        f"/projects/{seed.pid}/branches/main", headers=_auth(seed.owner)
    )
    assert r.status_code == 204
    assert "main" not in seed.branches()
