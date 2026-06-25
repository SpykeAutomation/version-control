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

from app.auth import create_org_with_owner, create_user  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.invites import create_invitation  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Organization, User  # noqa: E402
from fixtures_l5x import KITCHEN_SINK  # noqa: E402

# A password that satisfies the policy: >=12 chars with upper + lower + digit.
PW = "Abcdef123456"
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


def login(email: str) -> str:
    r = client.post("/auth/login", data={"username": email, "password": PW})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def make_owner(email: str, first: str, last: str, org_name: str) -> tuple[str, int]:
    """Bootstrap an org + its owner (admin path), then log in. Returns (token, org_id)."""
    db = SessionLocal()
    try:
        org, _owner = create_org_with_owner(
            db, name=org_name, owner_email=email,
            owner_first=first, owner_last=last, owner_password=PW,
        )
        org_id = org.id
    finally:
        db.close()
    return login(email), org_id


def make_user(email: str, first: str, last: str) -> str:
    """Create a plain account (no org), then log in."""
    db = SessionLocal()
    try:
        create_user(db, email=email, first_name=first, last_name=last, password=PW)
    finally:
        db.close()
    return login(email)


def _weak_password_rejected() -> bool:
    db = SessionLocal()
    try:
        create_user(db, email="weak@example.com", first_name="W", last_name="K",
                    password="short")
        return False
    except ValueError:
        return True
    finally:
        db.close()


def commit(pid: int, token: str, branch: str, title: str, text: str):
    return client.post(
        f"/projects/{pid}/commits",
        files={"file": (f"{title}.L5X", text, "application/octet-stream")},
        data={"branch": branch, "title": title, "description": "via smoke"},
        headers=auth(token),
    )


print("== auth & accounts ==")
alice, acme_id = make_owner("alice@example.com", "Alice", "Anderson", "Acme Mfg")
check("owner can log in", bool(alice))
me_data = client.get("/auth/me", headers=auth(alice)).json()
check("/auth/me returns first + last name",
      me_data["first_name"] == "Alice" and me_data["last_name"] == "Anderson")
check("owner is mapped to its organization", me_data["organization"] == "Acme Mfg")
check("weak password is rejected", _weak_password_rejected())

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

dresp = client.get(f"/projects/{pid}/diff?base=main&head=feature/gate", headers=auth(alice))
check("first diff computed (cache MISS)", dresp.headers.get("X-Cache") == "MISS")
diff = dresp.json()
check("diff shows MixerProg changed", [p["name"] for p in diff["programs"]] == ["MixerProg"])
check("diff shows a modified rung",
      diff["programs"][0]["routines"][0]["rungs"][0]["kind"] == "modified")
check("second identical diff served from cache (HIT)", client.get(
    f"/projects/{pid}/diff?base=main&head=feature/gate", headers=auth(alice)
).headers.get("X-Cache") == "HIT")

print("== ladder (visual) diff ==")
lad = client.get(f"/projects/{pid}/diff/ladder?base=main&head=feature/gate", headers=auth(alice))
check("ladder diff returns a LadderDocument", "routines" in lad.json())
check("ladder diff is cached too (HIT on repeat)", client.get(
    f"/projects/{pid}/diff/ladder?base=main&head=feature/gate", headers=auth(alice)
).headers.get("X-Cache") == "HIT")

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

bob = make_user("bob@example.com", "Bob", "Brown")
check("user without an organization shows null",
      client.get("/auth/me", headers=auth(bob)).json()["organization"] is None)
check("non-member is forbidden",
      client.get(f"/projects/{pid2}/pulls", headers=auth(bob)).status_code == 403)
client.post(f"/projects/{pid2}/members", json={"email": "bob@example.com"}, headers=auth(alice))
check("added member can now view", client.get(
    f"/projects/{pid2}/pulls", headers=auth(bob)).status_code == 200)
c = client.post(f"/projects/{pid2}/pulls/2/comments",
                json={"body": "Please rebase onto main."}, headers=auth(bob))
check("other user can comment", c.status_code == 201 and c.json()["author"]["first_name"] == "Bob")
check("comments list shows the comment", len(client.get(
    f"/projects/{pid2}/pulls/2/comments", headers=auth(alice)).json()) == 1)

print("== organization invites ==")
check("non-owner cannot invite", client.post(
    f"/orgs/{acme_id}/invites", json={"email": "x@acme.com"}, headers=auth(bob)
).status_code == 403)

invite = client.post(f"/orgs/{acme_id}/invites", json={"email": "carol@acme.com"},
                     headers=auth(alice))
check("owner can create an invite", invite.status_code == 201)
token = invite.json()["token"]

check("accept with the wrong email is rejected", client.post(
    f"/invites/{token}/accept",
    json={"email": "intruder@acme.com", "first_name": "I", "last_name": "I", "password": PW},
).status_code == 400)

accepted = client.post(f"/invites/{token}/accept", json={
    "email": "carol@acme.com", "first_name": "Carol", "last_name": "Cruz", "password": PW})
check("new user accepts and is issued a token",
      accepted.status_code == 200 and accepted.json()["access_token"])
carol = accepted.json()["access_token"]
check("invited user is mapped to the org",
      client.get("/auth/me", headers=auth(carol)).json()["organization"] == "Acme Mfg")

check("the same link cannot be reused", client.post(f"/invites/{token}/accept", json={
    "email": "carol@acme.com", "first_name": "Carol", "last_name": "Cruz", "password": PW}
).status_code == 400)

invite2 = client.post(f"/orgs/{acme_id}/invites", json={"email": "bob@example.com"},
                      headers=auth(alice)).json()
check("existing user accepts with just their email", client.post(
    f"/invites/{invite2['token']}/accept", json={"email": "bob@example.com"}
).status_code == 200)
check("existing user now shows the org",
      client.get("/auth/me", headers=auth(bob)).json()["organization"] == "Acme Mfg")

_db = SessionLocal()
try:
    _org = _db.get(Organization, acme_id)
    _owner = _db.get(User, _org.owner_id)
    expired_token, _ = create_invitation(
        _db, organization=_org, email="dan@acme.com", invited_by=_owner, ttl_days=-1)
finally:
    _db.close()
check("an expired invite is rejected", client.post(f"/invites/{expired_token}/accept", json={
    "email": "dan@acme.com", "first_name": "D", "last_name": "D", "password": PW}
).status_code == 400)

print("== malformed upload ==")
bad = commit(pid, alice, "main", "Garbage", "this is not an L5X file")
check("malformed upload returns 400 (not 500)", bad.status_code == 400)
check("error message is helpful", "parse" in bad.json()["detail"].lower())

print("== login rate limit ==")
burst = [
    client.post(
        "/auth/login", data={"username": "alice@example.com", "password": "nope"}
    ).status_code
    for _ in range(settings.login_rate_max + 5)
]
check("login rate limit returns 429 after the cap", 429 in burst)

print(f"\nALL {ok} CHECKS PASSED")
