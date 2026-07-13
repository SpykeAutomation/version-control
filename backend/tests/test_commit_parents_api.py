"""API tests for the `parents` field on commit listings: GET /commits returns
each commit's parent shas in git's order (first parent first), which is what
lets a client reconstruct branch topology — the trunk is the first-parent
chain and a merge commit's second parent opens the merged branch's side."""
import os
import tempfile

# Point the app at a throwaway data dir BEFORE any app module is imported —
# app.config builds its settings singleton (SQLite path, repos dir) at import.
# When another API test module imported first, its data dir simply wins.
os.environ["PLCVC_DATA_DIR"] = tempfile.mkdtemp(prefix="plcvc-parents-api-")

import pytest

# The engine-only environment (requirements-dev.txt) has no app stack; these
# API tests need it (requirements-app.txt). CI runs them in the api-tests job;
# the engine matrix skips this module instead of failing collection.
pytest.importorskip("fastapi", reason="API tests need requirements-app.txt")

from fastapi.testclient import TestClient

from app.auth import create_user
from app.db import SessionLocal
from app.main import app
from fixtures_l5x import KITCHEN_SINK

# Satisfies the password policy: >=12 chars with upper + lower + digit.
PW = "Abcdef123456"

CHANGE_X = KITCHEN_SINK.replace(
    "XIC(StartPB)OTE(RunLamp);", "XIC(StartPB)XIC(GateOk)OTE(RunLamp);"
)


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
    """main: A (root) -> B (adds bom.csv); a 'feature' branch off A with its
    own commit C (edits line.L5X, so it merges into B without conflict)."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.owner = _login(client, "parents-owner@example.com", "Par", "Owner")
        self.pid = client.post(
            "/projects", json={"name": "Parents Demo"}, headers=_auth(self.owner)
        ).json()["id"]
        self.sha_a = self.commit("main", "Initial import", [("line.L5X", KITCHEN_SINK)])
        r = client.post(
            f"/projects/{self.pid}/branches",
            json={"name": "feature", "start_point": "main"},
            headers=_auth(self.owner),
        )
        assert r.status_code == 201, r.text
        self.sha_b = self.commit("main", "Add BOM", [("bom.csv", "part,qty\nA,1\n")])
        self.sha_c = self.commit("feature", "Gate rung", [("line.L5X", CHANGE_X)])

    def commit(self, branch: str, title: str, files: list[tuple[str, str]]) -> str:
        r = self.client.post(
            f"/projects/{self.pid}/commits",
            files=[("files", (n, body, "application/octet-stream")) for n, body in files],
            data={"branch": branch, "title": title},
            headers=_auth(self.owner),
        )
        assert r.status_code == 201, r.text
        return r.json()["sha"]

    def log(self, branch: str) -> list[dict]:
        r = self.client.get(
            f"/projects/{self.pid}/commits?branch={branch}",
            headers=_auth(self.owner),
        )
        assert r.status_code == 200, r.text
        return r.json()


@pytest.fixture(scope="module")
def seed(client: TestClient) -> Seed:
    return Seed(client)


def test_root_commit_has_no_parents(client, seed):
    root = seed.log("main")[-1]
    assert root["sha"] == seed.sha_a
    assert root["parents"] == []


def test_normal_commit_lists_exactly_its_parent(client, seed):
    by_sha = {c["sha"]: c for c in seed.log("main")}
    assert by_sha[seed.sha_b]["parents"] == [seed.sha_a]
    feature = {c["sha"]: c for c in seed.log("feature")}
    assert feature[seed.sha_c]["parents"] == [seed.sha_a]


def test_branch_tip_listing_carries_parents(client, seed):
    r = client.get(f"/projects/{seed.pid}/branches", headers=_auth(seed.owner))
    assert r.status_code == 200, r.text
    tips = {b["name"]: b["latest_commit"] for b in r.json()}
    assert tips["feature"]["parents"] == [seed.sha_a]
    assert tips["main"]["parents"] == [seed.sha_a]


def test_merge_commit_lists_target_then_source_parent(client, seed):
    pr = client.post(
        f"/projects/{seed.pid}/pulls",
        json={"title": "Gate rung", "source_branch": "feature", "target_branch": "main"},
        headers=_auth(seed.owner),
    )
    assert pr.status_code == 201, pr.text
    r = client.post(
        f"/projects/{seed.pid}/pulls/{pr.json()['number']}/merge",
        headers=_auth(seed.owner),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "merged", body
    merged = seed.log("main")[0]
    assert merged["sha"] == body["merge_sha"]
    # First parent: the pre-merge target tip. Second: the source branch's tip.
    assert merged["parents"] == [seed.sha_b, seed.sha_c]
