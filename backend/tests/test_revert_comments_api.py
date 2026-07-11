"""API tests for POST /projects/{id}/revert (restore an earlier commit's state
as one new commit, optimistic-concurrency guarded) and the comment-threading
changes (replies at any depth on PRs; commit-page discussions sharing the
comments table and behavior)."""
import os
import tempfile

# Point the app at a throwaway data dir BEFORE any app module is imported —
# app.config builds its settings singleton (SQLite path, repos dir) at import.
# When another API test module imported first, its data dir simply wins.
os.environ["PLCVC_DATA_DIR"] = tempfile.mkdtemp(prefix="plcvc-revert-api-")

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
CHANGE_Y = KITCHEN_SINK.replace(
    "XIC(StartPB)OTE(RunLamp);", "XIC(StartPB)XIC(EStop)OTE(RunLamp);"
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
    """main: A (line.L5X) -> B (edited line.L5X + bom.csv); a 'side' branch off
    A with its own commit (a non-ancestor of main's tip); owner + plain member
    + outsider."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.owner = _login(client, "revert-owner@example.com", "Rex", "Owner")
        self.member = _login(client, "revert-member@example.com", "Mem", "Ber")
        self.outsider = _login(client, "revert-outsider@example.com", "Out", "Sider")
        self.pid = client.post(
            "/projects", json={"name": "Revert Demo"}, headers=_auth(self.owner)
        ).json()["id"]
        client.post(
            f"/projects/{self.pid}/members",
            json={"email": "revert-member@example.com"},
            headers=_auth(self.owner),
        )
        self.sha_a = self.commit("main", "Initial import", [("line.L5X", KITCHEN_SINK)])
        client.post(
            f"/projects/{self.pid}/branches",
            json={"name": "side", "start_point": "main"},
            headers=_auth(self.owner),
        )
        self.sha_b = self.commit(
            "main", "Edit + BOM",
            [("line.L5X", CHANGE_X), ("bom.csv", "part,qty\nA,1\n")],
        )
        self.sha_side = self.commit("side", "Side change", [("line.L5X", CHANGE_Y)])

    def commit(self, branch: str, title: str, files: list[tuple[str, str]]) -> str:
        r = self.client.post(
            f"/projects/{self.pid}/commits",
            files=[("files", (n, body, "application/octet-stream")) for n, body in files],
            data={"branch": branch, "title": title},
            headers=_auth(self.owner),
        )
        assert r.status_code == 201, r.text
        return r.json()["sha"]

    def revert(
        self, target: str, expected: str,
        *, branch="main", token=None, message=None, description=None,
    ):
        payload = {"branch": branch, "target_sha": target, "expected_tip_sha": expected}
        if message is not None:
            payload["message"] = message
        if description is not None:
            payload["description"] = description
        return self.client.post(
            f"/projects/{self.pid}/revert",
            json=payload,
            headers=_auth(token or self.owner),
        )

    def files_at(self, ref: str) -> set[str]:
        r = self.client.get(
            f"/projects/{self.pid}/files?ref={ref}", headers=_auth(self.owner)
        )
        return {f["path"] for f in r.json()["files"]}

    def raw_l5x(self, ref: str) -> bytes:
        return self.client.get(
            f"/projects/{self.pid}/files/raw?ref={ref}&path=l5x/line/source.L5X",
            headers=_auth(self.owner),
        ).content


@pytest.fixture(scope="module")
def seed(client: TestClient) -> Seed:
    return Seed(client)


# --- revert: failure modes first (they must not mutate the branch) -----------


def test_revert_validation_errors(client, seed):
    # Unknown branch -> 404.
    assert seed.revert(seed.sha_a, seed.sha_b, branch="ghost").status_code == 404
    # Unknown target -> 404.
    assert seed.revert("0" * 40, seed.sha_b).status_code == 404
    # Target is already the tip -> 400.
    r = seed.revert(seed.sha_b, seed.sha_b)
    assert r.status_code == 400 and "already the branch tip" in r.json()["detail"]
    # A commit that isn't an ancestor of the tip -> 400.
    r = seed.revert(seed.sha_side, seed.sha_b)
    assert r.status_code == 400 and "ancestor" in r.json()["detail"]
    # Stale expected tip -> 409, current tip in the detail.
    r = seed.revert(seed.sha_a, seed.sha_a)
    assert r.status_code == 409
    assert seed.sha_b in r.json()["detail"]
    # An unprotected branch reverts like it commits — any member. Proven
    # without moving the branch: the member sails past the permission gate
    # and fails on validation (target == tip), not on 403.
    r = seed.revert(seed.sha_b, seed.sha_b, token=seed.member)
    assert r.status_code == 400 and "already the branch tip" in r.json()["detail"]
    # A non-member stays 403.
    assert seed.revert(seed.sha_a, seed.sha_b, token=seed.outsider).status_code == 403
    # Nothing above moved the branch.
    tip = client.get(
        f"/projects/{seed.pid}/commits?branch=main", headers=_auth(seed.owner)
    ).json()[0]["sha"]
    assert tip == seed.sha_b


def test_protected_branch_blocks_commits_but_managers_can_revert(client, seed):
    client.post(
        f"/projects/{seed.pid}/branches",
        json={"name": "prot", "start_point": "main"},
        headers=_auth(seed.owner),
    )
    client.put(
        f"/projects/{seed.pid}/branches/prot/protection",
        json={"protected": True},
        headers=_auth(seed.owner),
    )
    # Direct commits to a protected branch are rejected — change reaches it
    # through a pull request.
    direct = client.post(
        f"/projects/{seed.pid}/commits",
        files=[("files", ("line.L5X", KITCHEN_SINK, "application/octet-stream"))],
        data={"branch": "prot", "title": "Direct commit"},
        headers=_auth(seed.owner),
    )
    assert direct.status_code == 400
    assert "protected" in direct.json()["detail"]
    # Revert is the sanctioned rollback: it works on a protected branch, but
    # only for a manager — a plain member is 403 regardless of protection.
    assert seed.revert(
        seed.sha_a, seed.sha_b, branch="prot", token=seed.member
    ).status_code == 403
    r = seed.revert(seed.sha_a, seed.sha_b, branch="prot")
    assert r.status_code == 201, r.text
    assert seed.files_at(r.json()["sha"]) == {"l5x/line"}
    # Unprotecting re-opens direct commits (and main, never explicitly
    # protected in this project, has been taking commits all along).
    client.put(
        f"/projects/{seed.pid}/branches/prot/protection",
        json={"protected": False},
        headers=_auth(seed.owner),
    )
    assert seed.commit("prot", "Now allowed", [("line.L5X", CHANGE_Y)])


# --- revert: happy path and follow-ons (each builds on the previous tip) -----


def test_revert_happy_path(client, seed):
    r = seed.revert(seed.sha_a, seed.sha_b)
    assert r.status_code == 201, r.text
    body = r.json()
    seed.sha_c = body["sha"]
    assert seed.sha_c not in (seed.sha_a, seed.sha_b)
    assert body["branch"] == "main"
    assert body["title"] == f'Revert to {seed.sha_a[:7]} "Initial import"'
    # The tip advanced by exactly one commit and history is intact: A and B
    # are both still in the log, newest first.
    commits = client.get(
        f"/projects/{seed.pid}/commits?branch=main", headers=_auth(seed.owner)
    ).json()
    assert [c["sha"] for c in commits] == [seed.sha_c, seed.sha_b, seed.sha_a]
    # The new tip's state is byte-identical to the target's: the file added
    # since A is gone and the L5X matches A's exact bytes.
    assert seed.files_at(seed.sha_c) == seed.files_at(seed.sha_a) == {"l5x/line"}
    assert seed.raw_l5x(seed.sha_c) == KITCHEN_SINK.encode()


def test_identical_trees_rejected(client, seed):
    # The tip's tree already equals A's tree after the revert.
    r = seed.revert(seed.sha_a, seed.sha_c)
    assert r.status_code == 400
    assert "Nothing to revert" in r.json()["detail"]


def test_revert_of_a_revert_restores_original_state(client, seed):
    # Performed by a plain member: main carries no protection row, so revert
    # needs only membership — same as committing to it.
    r = seed.revert(
        seed.sha_b, seed.sha_c, message="Bring back the BOM",
        description="Batch 7 passed QA on the old program after all.",
        token=seed.member,
    )
    assert r.status_code == 201, r.text
    seed.sha_d = r.json()["sha"]
    assert r.json()["title"] == "Bring back the BOM"
    assert seed.files_at(seed.sha_d) == {"l5x/line", "files/bom.csv"}
    assert seed.raw_l5x(seed.sha_d) == CHANGE_X.encode()
    # The optional description travels into the commit body.
    detail = client.get(
        f"/projects/{seed.pid}/commits/{seed.sha_d}", headers=_auth(seed.owner)
    ).json()
    assert detail["description"] == "Batch 7 passed QA on the old program after all."


def test_upload_after_revert_does_not_resurrect_removed_files(client, seed):
    # Revert away the BOM again, then make a normal upload commit: the file
    # removed by the revert must NOT reappear (the repo layer realigns the
    # checked-out working tree with the moved ref).
    r = seed.revert(seed.sha_a, seed.sha_d)
    assert r.status_code == 201, r.text
    sha_e = r.json()["sha"]
    assert "files/bom.csv" not in seed.files_at(sha_e)
    sha_f = seed.commit("main", "Post-revert edit", [("line.L5X", CHANGE_Y)])
    files = seed.files_at(sha_f)
    assert "files/bom.csv" not in files
    assert seed.raw_l5x(sha_f) == CHANGE_Y.encode()


def test_owner_alone_reopens_the_default_branch(client, seed):
    """Protecting the default branch must be reversible — but only by the
    project owner, not an admin. Once unprotected (row deleted), the default
    branch takes direct commits and member reverts again."""
    put = f"/projects/{seed.pid}/branches/main/protection"
    r = client.put(
        put, json={"protected": True, "required_approvals": 1}, headers=_auth(seed.owner)
    )
    assert r.status_code == 200 and r.json()["required_approvals"] == 1
    # Protected main now rejects direct commits and member reverts.
    blocked = client.post(
        f"/projects/{seed.pid}/commits",
        files=[("files", ("line.L5X", KITCHEN_SINK, "application/octet-stream"))],
        data={"branch": "main", "title": "Direct"},
        headers=_auth(seed.owner),
    )
    assert blocked.status_code == 400
    assert seed.revert(seed.sha_a, seed.sha_b, token=seed.member).status_code == 403
    # An admin cannot reopen the default branch — the owner alone can.
    members = client.get(
        f"/projects/{seed.pid}/members", headers=_auth(seed.owner)
    ).json()
    member_id = next(
        m["id"] for m in members if m["email"] == "revert-member@example.com"
    )
    client.patch(
        f"/projects/{seed.pid}/members/{member_id}", json={"role": "admin"},
        headers=_auth(seed.owner),
    )
    denied = client.put(put, json={"protected": False}, headers=_auth(seed.member))
    assert denied.status_code == 403
    assert "owner" in denied.json()["detail"].lower()
    client.patch(  # restore the seed's role assumptions for later tests
        f"/projects/{seed.pid}/members/{member_id}", json={"role": "member"},
        headers=_auth(seed.owner),
    )
    reopened = client.put(put, json={"protected": False}, headers=_auth(seed.owner))
    assert reopened.status_code == 200
    assert reopened.json()["required_approvals"] == 0
    # Direct commits flow again, and a member sails past the revert gate
    # (failing on validation, not 403).
    sha = seed.commit("main", "Reopened", [("line.L5X", KITCHEN_SINK)])
    r = seed.revert(sha, sha, token=seed.member)
    assert r.status_code == 400 and "already the branch tip" in r.json()["detail"]


# --- comments: PR replies at any depth ----------------------------------------


def test_pr_reply_chain_any_depth(client, seed):
    pr = client.post(
        f"/projects/{seed.pid}/pulls",
        json={"title": "Side", "source_branch": "side", "target_branch": "main"},
        headers=_auth(seed.owner),
    ).json()
    n = pr["number"]
    url = f"/projects/{seed.pid}/pulls/{n}/comments"
    c1 = client.post(url, json={"body": "top"}, headers=_auth(seed.owner)).json()
    c2 = client.post(
        url, json={"body": "reply", "parent_id": c1["id"]}, headers=_auth(seed.member)
    ).json()
    r3 = client.post(
        url, json={"body": "reply to reply", "parent_id": c2["id"]},
        headers=_auth(seed.owner),
    )
    # Previously 400 "Replies are only one level deep" — now the true parent
    # is stored at any depth.
    assert r3.status_code == 201, r3.text
    assert r3.json()["parent_id"] == c2["id"]
    seed.pr_comment_id = c1["id"]  # reused by the cross-scope parent test
    # Regression guard: inviting a reviewer exercises membership_role directly
    # (the comments refactor once dropped that import; only the smoke run
    # caught it — keep it covered here).
    rv = client.post(
        f"/projects/{seed.pid}/pulls/{n}/reviewers",
        json={"email": "revert-member@example.com"},
        headers=_auth(seed.owner),
    )
    assert rv.status_code == 201, rv.text


# --- comments: commit-page discussions ----------------------------------------


def _curl(seed, sha):
    return f"/projects/{seed.pid}/commits/{sha}/comments"


def test_commit_comment_crud_roundtrip_short_and_full_sha(client, seed):
    # POST against a short sha; the comment is stored under the full sha.
    created = client.post(
        _curl(seed, seed.sha_a[:8]),
        json={"body": "first!", "anchor": {"path": "l5x/line", "routine": "Main", "rung": 0, "sha": seed.sha_a}},
        headers=_auth(seed.member),
    )
    assert created.status_code == 201, created.text
    cid = created.json()["id"]
    assert created.json()["anchor"]["routine"] == "Main"
    # GET with the full sha finds it; short-sha GET converges on the same row.
    full = client.get(_curl(seed, seed.sha_a), headers=_auth(seed.owner))
    assert [c["id"] for c in full.json()] == [cid]
    short = client.get(_curl(seed, seed.sha_a[:8]), headers=_auth(seed.owner))
    assert [c["id"] for c in short.json()] == [cid]
    # Resolve: any member. Body edit: author only.
    assert client.patch(
        f"{_curl(seed, seed.sha_a)}/{cid}", json={"resolved": True},
        headers=_auth(seed.owner),
    ).json()["resolved"] is True
    denied = client.patch(
        f"{_curl(seed, seed.sha_a)}/{cid}", json={"body": "hax"},
        headers=_auth(seed.owner),
    )
    assert denied.status_code == 403
    edited = client.patch(
        f"{_curl(seed, seed.sha_a)}/{cid}", json={"body": "first! (edited)"},
        headers=_auth(seed.member),
    ).json()
    assert edited["body"] == "first! (edited)" and edited["edited_at"] is not None
    # Delete: a manager may delete the member's comment.
    assert client.delete(
        f"{_curl(seed, seed.sha_a)}/{cid}", headers=_auth(seed.owner)
    ).status_code == 204
    assert client.get(_curl(seed, seed.sha_a), headers=_auth(seed.owner)).json() == []


def test_commit_comment_parent_must_share_the_discussion(client, seed):
    on_b = client.post(
        _curl(seed, seed.sha_b), json={"body": "on B"}, headers=_auth(seed.owner)
    ).json()
    # Parent living on another commit's discussion -> 400.
    r = client.post(
        _curl(seed, seed.sha_a),
        json={"body": "cross-commit", "parent_id": on_b["id"]},
        headers=_auth(seed.owner),
    )
    assert r.status_code == 400
    # Parent living on a PR discussion -> 400 too.
    r = client.post(
        _curl(seed, seed.sha_a),
        json={"body": "cross-scope", "parent_id": seed.pr_comment_id},
        headers=_auth(seed.owner),
    )
    assert r.status_code == 400


def test_commit_comment_unknown_sha_and_non_member(client, seed):
    assert client.get(
        _curl(seed, "0" * 40), headers=_auth(seed.owner)
    ).status_code == 404
    assert client.post(
        _curl(seed, "not-a-ref"), json={"body": "x"}, headers=_auth(seed.owner)
    ).status_code == 404
    assert client.get(
        _curl(seed, seed.sha_a), headers=_auth(seed.outsider)
    ).status_code == 403
    assert client.post(
        _curl(seed, seed.sha_a), json={"body": "x"}, headers=_auth(seed.outsider)
    ).status_code == 403


def test_deleting_a_comment_cascades_to_its_reply_subtree(client, seed):
    url = _curl(seed, seed.sha_c)
    c1 = client.post(url, json={"body": "1"}, headers=_auth(seed.owner)).json()
    c2 = client.post(
        url, json={"body": "2", "parent_id": c1["id"]}, headers=_auth(seed.member)
    ).json()
    c3 = client.post(
        url, json={"body": "3", "parent_id": c2["id"]}, headers=_auth(seed.owner)
    )
    assert c3.status_code == 201  # any depth on commit discussions too
    assert client.delete(
        f"{url}/{c1['id']}", headers=_auth(seed.owner)
    ).status_code == 204
    listing = client.get(url, headers=_auth(seed.owner))
    assert listing.json() == []
    assert listing.headers["X-Total-Count"] == "0"


def test_commit_comment_pagination_and_total(client, seed):
    url = _curl(seed, seed.sha_d)
    for i in range(3):
        assert client.post(
            url, json={"body": f"c{i}"}, headers=_auth(seed.owner)
        ).status_code == 201
    page1 = client.get(f"{url}?limit=2&offset=0", headers=_auth(seed.owner))
    assert page1.headers["X-Total-Count"] == "3"
    assert [c["body"] for c in page1.json()] == ["c0", "c1"]
    page2 = client.get(f"{url}?limit=2&offset=2", headers=_auth(seed.owner))
    assert page2.headers["X-Total-Count"] == "3"
    assert [c["body"] for c in page2.json()] == ["c2"]
