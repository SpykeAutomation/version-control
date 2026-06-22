"""End-to-end smoke test of the API, in-process via TestClient.

Doubles as a worked example of the request flow for the frontend. Run with:
    PLCVC_DATA_DIR=$(mktemp -d) .venv/bin/python scripts/smoke_api.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "tests"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from fixtures_l5x import KITCHEN_SINK  # noqa: E402

BASE = KITCHEN_SINK
CHANGE_X = KITCHEN_SINK.replace(
    "XIC(StartPB)OTE(RunLamp);", "XIC(StartPB)XIC(GateOk)OTE(RunLamp);"
)
CHANGE_Y = KITCHEN_SINK.replace(
    "XIC(StartPB)OTE(RunLamp);", "XIC(StartPB)XIC(EStop)OTE(RunLamp);"
)

client = TestClient(app)
ok = 0


def check(label: str, condition: bool) -> None:
    global ok
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {label}")
    if condition:
        ok += 1
    else:
        raise SystemExit(f"smoke failed at: {label}")


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def register(email: str, name: str) -> str:
    r = client.post(
        "/auth/register", json={"email": email, "name": name, "password": "pw123456"}
    )
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


def commit(pid: int, token: str, branch: str, title: str, text: str):
    return client.post(
        f"/projects/{pid}/commits",
        files={"file": (f"{title}.L5X", text, "application/octet-stream")},
        data={"branch": branch, "title": title, "description": "via smoke"},
        headers=auth(token),
    )


print("== auth & project ==")
alice = register("alice@example.com", "Alice")
check("register returns token", bool(alice))
check("login works", client.post(
    "/auth/login", data={"username": "alice@example.com", "password": "pw123456"}
).status_code == 200)
check("/auth/me", client.get("/auth/me", headers=auth(alice)).json()["email"] == "alice@example.com")

pid = client.post("/projects", json={"name": "Mixer Line 1"}, headers=auth(alice)).json()["id"]
check("project created with main branch",
      client.get(f"/projects/{pid}", headers=auth(alice)).json()["branches"] == ["main"])

print("== commits, branches, diff ==")
check("initial commit on main", commit(pid, alice, "main", "Initial import", BASE).status_code == 201)
check("create feature branch", client.post(
    f"/projects/{pid}/branches", json={"name": "feature/gate", "start_point": "main"},
    headers=auth(alice)).status_code == 201)
check("commit on branch", commit(pid, alice, "feature/gate", "Add gate permissive", CHANGE_X).status_code == 201)
check("commit history on main", len(client.get(
    f"/projects/{pid}/commits?branch=main", headers=auth(alice)).json()) == 1)

diff = client.get(f"/projects/{pid}/diff?base=main&head=feature/gate", headers=auth(alice)).json()
check("diff shows MixerProg changed", [p["name"] for p in diff["programs"]] == ["MixerProg"])
check("diff shows a modified rung",
      diff["programs"][0]["routines"][0]["rungs"][0]["kind"] == "modified")

print("== pull request & clean merge ==")
pr = client.post(f"/projects/{pid}/pulls", json={
    "title": "Add gate permissive", "description": "Safety gate",
    "source_branch": "feature/gate", "target_branch": "main"}, headers=auth(alice)).json()
check("PR created as #1", pr["number"] == 1 and pr["status"] == "open")
check("PR diff endpoint", bool(client.get(
    f"/projects/{pid}/pulls/1/diff", headers=auth(alice)).json()["programs"]))
merge = client.post(f"/projects/{pid}/pulls/1/merge", headers=auth(alice)).json()
check("clean merge succeeds", merge["status"] == "merged" and merge["merge_sha"])

print("== conflict + comments from another user ==")
pid2 = client.post("/projects", json={"name": "Conflict Demo"}, headers=auth(alice)).json()["id"]
commit(pid2, alice, "main", "Base", BASE)
for b in ("branch-a", "branch-b"):
    client.post(f"/projects/{pid2}/branches", json={"name": b, "start_point": "main"}, headers=auth(alice))
commit(pid2, alice, "branch-a", "Change A", CHANGE_X)
commit(pid2, alice, "branch-b", "Change B", CHANGE_Y)
client.post(f"/projects/{pid2}/pulls", json={"title": "A", "source_branch": "branch-a", "target_branch": "main"}, headers=auth(alice))
client.post(f"/projects/{pid2}/pulls", json={"title": "B", "source_branch": "branch-b", "target_branch": "main"}, headers=auth(alice))
check("first PR merges clean", client.post(
    f"/projects/{pid2}/pulls/1/merge", headers=auth(alice)).json()["status"] == "merged")
conflict = client.post(f"/projects/{pid2}/pulls/2/merge", headers=auth(alice)).json()
check("second PR reports conflict (not error)", conflict["status"] == "conflict")
check("conflict message is human-readable", "resolve" in conflict["message"].lower())

bob = register("bob@example.com", "Bob")
check("non-member is forbidden",
      client.get(f"/projects/{pid2}/pulls", headers=auth(bob)).status_code == 403)
client.post(f"/projects/{pid2}/members", json={"email": "bob@example.com"}, headers=auth(alice))
check("added member can now view", client.get(
    f"/projects/{pid2}/pulls", headers=auth(bob)).status_code == 200)
c = client.post(f"/projects/{pid2}/pulls/2/comments",
                json={"body": "Please rebase onto main."}, headers=auth(bob))
check("other user can comment", c.status_code == 201 and c.json()["author"]["name"] == "Bob")
check("comments list shows the comment", len(client.get(
    f"/projects/{pid2}/pulls/2/comments", headers=auth(alice)).json()) == 1)

print("== malformed upload ==")
bad = commit(pid, alice, "main", "Garbage", "this is not an L5X file")
check("malformed upload returns 400 (not 500)", bad.status_code == 400)
check("error message is helpful", "parse" in bad.json()["detail"].lower())

print(f"\nALL {ok} CHECKS PASSED")
