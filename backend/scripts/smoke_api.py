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


def commit(pid: int, token: str, branch: str, title: str, text: str,
           fname: str = "line.L5X"):
    """Upload a single L5X. A stable filename versions the same logical file."""
    return client.post(
        f"/projects/{pid}/commits",
        files=[("files", (fname, text, "application/octet-stream"))],
        data={"branch": branch, "title": title, "description": "via smoke"},
        headers=auth(token),
    )


def find_node(node: dict, pred):
    """Depth-first search of an organizer tree for the first node matching pred."""
    if pred(node):
        return node
    for child in node.get("children", []):
        hit = find_node(child, pred)
        if hit is not None:
            return hit
    return None


print("== auth & accounts ==")
alice, acme_id = make_owner("alice@example.com", "Alice", "Anderson", "Acme Mfg")
check("owner can log in", bool(alice))
me_data = client.get("/auth/me", headers=auth(alice)).json()
check("/auth/me returns first + last name",
      me_data["first_name"] == "Alice" and me_data["last_name"] == "Anderson")
check("owner is mapped to its organization", me_data["organization"] == "Acme Mfg")
check("weak password is rejected", _weak_password_rejected())

print("== CLI device authorization (RFC 8628) ==")
dc = client.post("/auth/device/code").json()
check("device-code request returns a device_code + user_code",
      bool(dc.get("device_code")) and bool(dc.get("user_code")))
check("polling before approval returns authorization_pending (400)", client.post(
      "/auth/device/token", json={"device_code": dc["device_code"]}).status_code == 400)
check("approving requires a logged-in user (401 without a token)", client.post(
      "/auth/device/approve", json={"user_code": dc["user_code"]}).status_code == 401)
check("an unknown user_code is rejected (400)", client.post(
      "/auth/device/approve", json={"user_code": "ZZZZ-ZZZZ"}, headers=auth(alice)).status_code == 400)
check("the logged-in user approves the device code (200)", client.post(
      "/auth/device/approve", json={"user_code": dc["user_code"]}, headers=auth(alice)).status_code == 200)
_issued = client.post("/auth/device/token", json={"device_code": dc["device_code"]})
check("after approval the CLI receives a token",
      _issued.status_code == 200 and bool(_issued.json()["access_token"]))
check("the device token authenticates as the approving user",
      client.get("/auth/me", headers=auth(_issued.json()["access_token"])
                 ).json()["email"] == "alice@example.com")
check("the device code is one-time (a second poll fails)", client.post(
      "/auth/device/token", json={"device_code": dc["device_code"]}).status_code == 400)
check("a used user_code cannot be approved again (409)", client.post(
      "/auth/device/approve", json={"user_code": dc["user_code"]}, headers=auth(alice)).status_code == 409)

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

# The project-wide diff is now a manifest of changed files; drill in per file.
mresp = client.get(f"/projects/{pid}/diff?base=main&head=feature/gate", headers=auth(alice))
check("manifest computed (cache MISS)", mresp.headers.get("X-Cache") == "MISS")
manifest = mresp.json()["files"]
check("manifest lists line.L5X as modified", any(
    f["path"] == "l5x/line" and f["change"] == "modified" for f in manifest))
check("manifest cached (HIT on repeat)", client.get(
    f"/projects/{pid}/diff?base=main&head=feature/gate", headers=auth(alice)
).headers.get("X-Cache") == "HIT")

dresp = client.get(
    f"/projects/{pid}/diff/changeset?base=main&head=feature/gate&path=l5x/line",
    headers=auth(alice))
check("per-file changeset computed (cache MISS)", dresp.headers.get("X-Cache") == "MISS")
diff = dresp.json()
check("diff shows MixerProg changed", [p["name"] for p in diff["programs"]] == ["MixerProg"])
check("diff shows a modified rung",
      diff["programs"][0]["routines"][0]["rungs"][0]["kind"] == "modified")
check("changeset served from cache (HIT)", client.get(
    f"/projects/{pid}/diff/changeset?base=main&head=feature/gate&path=l5x/line",
    headers=auth(alice)).headers.get("X-Cache") == "HIT")

print("== ladder (visual) diff ==")
lad = client.get(
    f"/projects/{pid}/diff/ladder?base=main&head=feature/gate&path=l5x/line",
    headers=auth(alice))
check("ladder diff returns a LadderDocument", "routines" in lad.json())
check("ladder diff is cached too (HIT on repeat)", client.get(
    f"/projects/{pid}/diff/ladder?base=main&head=feature/gate&path=l5x/line",
    headers=auth(alice)).headers.get("X-Cache") == "HIT")

print("== organizer tree (nested, per L5X file) ==")
gate_sha = client.get(
    f"/projects/{pid}/commits?branch=feature/gate", headers=auth(alice)).json()[0]["sha"]
tr = client.get(f"/projects/{pid}/commits/{gate_sha}/tree?path=l5x/line", headers=auth(alice))
check("organizer tree computed (cache MISS)", tr.headers.get("X-Cache") == "MISS")
root = tr.json()["root"]
check("tree root is the controller", root["kind"] == "controller")
check("tree has a Programs folder", any(
    c["kind"] == "folder" and c["label"] == "Programs" for c in root["children"]))
mod_routine = find_node(root, lambda n: n["kind"] == "routine" and n["status"] == "modified")
check("the changed routine is flagged modified, with ladder identity",
      mod_routine is not None and mod_routine["routine"] == "Main"
      and mod_routine["controller"] is not None)
check("organizer tree is cached (HIT on repeat)", client.get(
    f"/projects/{pid}/commits/{gate_sha}/tree?path=l5x/line",
    headers=auth(alice)).headers.get("X-Cache") == "HIT")
check("ref-range organizer tree also builds", client.get(
    f"/projects/{pid}/tree?base=main&head=feature/gate&path=l5x/line",
    headers=auth(alice)).json()["root"]["kind"] == "controller")

print("== multi-file upload, per-file diff, text diff, raw download ==")
mpid = client.post("/projects", json={"name": "Multi Line"}, headers=auth(alice)).json()["id"]
up = client.post(
    f"/projects/{mpid}/commits",
    files=[
        ("files", ("lineA.L5X", BASE, "application/octet-stream")),
        ("files", ("lineB.L5X", BASE, "application/octet-stream")),
        ("files", ("bom.csv", "part,qty\nA,1\n", "text/csv")),
    ],
    data={"branch": "main", "title": "Import two lines + BOM"},
    headers=auth(alice),
)
check("multi-file upload commits once", up.status_code == 201)
tree = {f["path"] for f in client.get(
    f"/projects/{mpid}/files?ref=main", headers=auth(alice)).json()["files"]}
check("project lists both L5X files and the CSV",
      tree == {"l5x/lineA", "l5x/lineB", "files/bom.csv"})

client.post(f"/projects/{mpid}/branches", json={"name": "edit", "start_point": "main"},
            headers=auth(alice))
up2 = client.post(
    f"/projects/{mpid}/commits",
    files=[
        ("files", ("lineA.L5X", CHANGE_X, "application/octet-stream")),
        ("files", ("bom.csv", "part,qty\nA,2\nB,5\n", "text/csv")),
    ],
    data={"branch": "edit", "title": "Tweak line A + BOM"},
    headers=auth(alice),
)
check("second multi-file commit", up2.status_code == 201)

by_path = {f["path"]: f for f in client.get(
    f"/projects/{mpid}/diff?base=main&head=edit", headers=auth(alice)).json()["files"]}
check("manifest marks line A modified", by_path.get("l5x/lineA", {}).get("change") == "modified")
check("manifest marks the CSV modified", by_path.get("files/bom.csv", {}).get("change") == "modified")
check("manifest omits the unchanged line B", "l5x/lineB" not in by_path)

td = client.get(f"/projects/{mpid}/diff/text?base=main&head=edit&path=files/bom.csv",
                headers=auth(alice)).json()
check("text diff is not binary and has a unified body",
      td["binary"] is False and "B,5" in (td["unified"] or ""))

raw = client.get(f"/projects/{mpid}/files/raw?ref=main&path=l5x/lineA/source.L5X",
                 headers=auth(alice))
check("raw download returns the original L5X bytes",
      raw.status_code == 200 and raw.content == BASE.encode())

bad = client.post(
    f"/projects/{mpid}/commits",
    files=[
        ("files", ("good.L5X", CHANGE_Y, "application/octet-stream")),
        ("files", ("bad.L5X", "<not an l5x/>", "application/octet-stream")),
    ],
    data={"branch": "edit", "title": "Bad batch"},
    headers=auth(alice),
)
check("a batch with one bad L5X is rejected (400)", bad.status_code == 400)
check("nothing from the rejected batch was committed", "l5x/good" not in {
    f["path"] for f in client.get(
        f"/projects/{mpid}/files?ref=edit", headers=auth(alice)).json()["files"]})

# Per-file size limit. Lower it temporarily so we needn't actually send 100 MB.
_saved_limit = settings.max_upload_mb
settings.max_upload_mb = 0  # any non-empty file now exceeds the cap
toobig = client.post(
    f"/projects/{mpid}/commits",
    files=[("files", ("big.csv", "x" * 4096, "text/csv"))],
    data={"branch": "edit", "title": "Too big"},
    headers=auth(alice),
)
settings.max_upload_mb = _saved_limit
check("a file over the per-file size limit is rejected (413)", toobig.status_code == 413)

print("== pull request & clean merge ==")
pr = client.post(f"/projects/{pid}/pulls", json={
    "title": "Add gate permissive", "description": "Safety gate",
    "source_branch": "feature/gate", "target_branch": "main"}, headers=auth(alice)).json()
check("PR created as #1", pr["number"] == 1 and pr["status"] == "open")
check("PR diff manifest lists the changed file", any(
    f["path"] == "l5x/line" for f in client.get(
        f"/projects/{pid}/pulls/1/diff", headers=auth(alice)).json()["files"]))
merge = client.post(f"/projects/{pid}/pulls/1/merge", headers=auth(alice)).json()
check("clean merge succeeds", merge["status"] == "merged" and merge["merge_sha"])
_main_tip = client.get(f"/projects/{pid}/commits?branch=main", headers=auth(alice)).json()[0]
check("the merge commit is attributed to the acting user (not the system identity)",
      _main_tip["title"].startswith("Merge pull request #1")
      and _main_tip["author"] == "Alice Anderson")

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

print("== nested file paths + listing metadata ==")
nest = client.post("/projects", json={"name": "Nested"}, headers=auth(alice)).json()["id"]
nest_up = client.post(
    f"/projects/{nest}/commits",
    files=[
        ("files", ("ctrl.L5X", BASE, "application/octet-stream")),
        ("files", ("docs/specs/io.csv", "tag,addr\nA,1\n", "text/csv")),
        ("files", ("docs/readme.md", "# Nested", "text/markdown")),
    ],
    data={"branch": "main", "title": "Seed nested"},
    headers=auth(alice),
)
check("nested multi-file upload commits", nest_up.status_code == 201)
listing = client.get(f"/projects/{nest}/files?ref=main", headers=auth(alice)).json()["files"]
by_path = {f["path"]: f for f in listing}
check("nested folder structure is preserved",
      "files/docs/specs/io.csv" in by_path and "files/docs/readme.md" in by_path)
check("the L5X stays one logical entry", "l5x/ctrl" in by_path)
check("listing reports each file's size", by_path["files/docs/specs/io.csv"]["size"] > 0)
check("listing reports who last changed it (the real uploader)",
      by_path["files/docs/specs/io.csv"]["modified_by"] == "Alice Anderson")
check("listing reports when it was last changed",
      bool(by_path["files/docs/specs/io.csv"]["modified_at"]))
check("a nested file downloads by its full path",
      client.get(f"/projects/{nest}/files/raw?ref=main&path=files/docs/readme.md",
                 headers=auth(alice)).content == b"# Nested")
escape = client.post(
    f"/projects/{nest}/commits",
    files=[("files", ("../escape.txt", "x", "text/plain"))],
    data={"branch": "main", "title": "escape"},
    headers=auth(alice),
)
check("a path-traversal upload is rejected (400)", escape.status_code == 400)

print("== project description, owner name, your_role ==")
alice_id = client.get("/auth/me", headers=auth(alice)).json()["id"]
created = client.post("/projects", json={
    "name": "Documented Line", "description": "Main bottling line"}, headers=auth(alice)).json()
dpid = created["id"]
check("create returns the description", created["description"] == "Main bottling line")
check("create returns the owner's name, not just an id",
      created["owner"]["first_name"] == "Alice")
check("create reports the caller's role as owner", created["your_role"] == "owner")
check("description persists on fetch", client.get(
    f"/projects/{dpid}", headers=auth(alice)).json()["description"] == "Main bottling line")

print("== rename / update settings ==")
patched = client.patch(f"/projects/{dpid}", json={
    "name": "Bottling Line 1", "description": "Renamed"}, headers=auth(alice))
check("owner can rename + edit description",
      patched.status_code == 200 and patched.json()["name"] == "Bottling Line 1"
      and patched.json()["description"] == "Renamed")
check("rename re-slugs", patched.json()["slug"] == "bottling-line-1")

print("== roles: owner / admin / member ==")
add_admin = client.post(f"/projects/{dpid}/members",
                        json={"email": "bob@example.com", "role": "admin"}, headers=auth(alice))
check("owner can add an admin", add_admin.status_code == 201 and add_admin.json()["role"] == "admin")
carol_id = client.post(f"/projects/{dpid}/members",
                       json={"email": "carol@acme.com", "role": "member"}, headers=auth(alice)).json()["id"]
erin = make_user("erin@example.com", "Erin", "Eve")
check("admin can add a member", client.post(f"/projects/{dpid}/members",
      json={"email": "erin@example.com"}, headers=auth(bob)).status_code == 201)
check("a plain member cannot add members", client.post(f"/projects/{dpid}/members",
      json={"email": "erin@example.com"}, headers=auth(carol)).status_code == 403)
check("a plain member cannot rename", client.patch(f"/projects/{dpid}",
      json={"name": "Nope"}, headers=auth(erin)).status_code == 403)
check("a plain member can still upload",
      commit(dpid, carol, "main", "Carol import", BASE).status_code == 201)
check("manager can change a member's role", client.patch(
      f"/projects/{dpid}/members/{carol_id}", json={"role": "admin"}, headers=auth(alice)
      ).status_code == 200)
check("an admin cannot remove another admin (owner only)", client.delete(
      f"/projects/{dpid}/members/{carol_id}", headers=auth(bob)).status_code == 403)
check("the owner can remove an admin", client.delete(
      f"/projects/{dpid}/members/{carol_id}", headers=auth(alice)).status_code == 204)
check("the project owner cannot be removed", client.delete(
      f"/projects/{dpid}/members/{alice_id}", headers=auth(alice)).status_code == 400)

print("== repository overview ==")
ov = client.get(f"/projects/{dpid}/overview", headers=auth(alice)).json()
check("overview reports file totals", ov["file_count"] >= 1 and ov["l5x_count"] >= 1)
check("overview surfaces the controller name", ov["controller_name"] is not None)
check("overview reports the latest commit", ov["latest_commit"]["title"] == "Carol import")

print("== unresolved comments + resolve ==")
client.post(f"/projects/{dpid}/branches", json={"name": "feat", "start_point": "main"},
            headers=auth(alice))
commit(dpid, alice, "feat", "tweak", CHANGE_X)
prn = client.post(f"/projects/{dpid}/pulls", json={
    "title": "Tweak", "source_branch": "feat", "target_branch": "main"},
    headers=auth(alice)).json()["number"]
cm = client.post(f"/projects/{dpid}/pulls/{prn}/comments",
                 json={"body": "please review"}, headers=auth(alice)).json()
check("a new comment is unresolved by default", cm["resolved"] is False)
ov2 = client.get(f"/projects/{dpid}/overview", headers=auth(alice)).json()
check("overview counts the open PR and unresolved comment",
      ov2["open_pull_count"] == 1 and ov2["unresolved_comment_count"] == 1)
res = client.patch(f"/projects/{dpid}/pulls/{prn}/comments/{cm['id']}",
                   json={"resolved": True}, headers=auth(alice))
check("a comment can be resolved", res.status_code == 200 and res.json()["resolved"] is True)
check("resolving drops the unresolved count", client.get(
      f"/projects/{dpid}/overview", headers=auth(alice)).json()["unresolved_comment_count"] == 0)

print("== enriched branches, protection, commit detail, releases ==")
fpid = client.post("/projects", json={"name": "Feature Demo"}, headers=auth(alice)).json()["id"]
commit(fpid, alice, "main", "Initial import", BASE)
client.post(f"/projects/{fpid}/members", json={"email": "erin@example.com"}, headers=auth(alice))
client.post(f"/projects/{fpid}/branches", json={"name": "feature/x", "start_point": "main"},
            headers=auth(alice))
commit(fpid, alice, "feature/x", "Work on x", CHANGE_X)

branches = {b["name"]: b for b in client.get(
    f"/projects/{fpid}/branches", headers=auth(alice)).json()}
check("branches endpoint returns enriched objects", isinstance(branches["main"], dict))
check("main is the default branch and protected",
      branches["main"]["is_default"] and branches["main"]["is_protected"])
check("feature branch carries its tip commit",
      branches["feature/x"]["latest_commit"]["title"] == "Work on x")
check("feature branch is 1 ahead / 0 behind and not merged",
      branches["feature/x"]["ahead"] == 1 and branches["feature/x"]["behind"] == 0
      and branches["feature/x"]["merged"] is False)

# Protection + delete on a throwaway branch (leave feature/x intact).
client.post(f"/projects/{fpid}/branches", json={"name": "scratch", "start_point": "main"},
            headers=auth(alice))
check("a plain member cannot protect a branch (manager only)", client.put(
      f"/projects/{fpid}/branches/scratch/protection", json={"protected": True},
      headers=auth(erin)).status_code == 403)
check("a manager can protect a branch", client.put(
      f"/projects/{fpid}/branches/scratch/protection", json={"protected": True},
      headers=auth(alice)).json()["is_protected"] is True)
check("a protected branch cannot be deleted (400)", client.delete(
      f"/projects/{fpid}/branches/scratch", headers=auth(alice)).status_code == 400)
check("the default branch cannot be deleted (400)", client.delete(
      f"/projects/{fpid}/branches/main", headers=auth(alice)).status_code == 400)
client.put(f"/projects/{fpid}/branches/scratch/protection", json={"protected": False},
           headers=auth(alice))
check("a member can delete an unprotected branch (204)", client.delete(
      f"/projects/{fpid}/branches/scratch", headers=auth(erin)).status_code == 204)
check("the deleted branch is gone", "scratch" not in {b["name"] for b in client.get(
      f"/projects/{fpid}/branches", headers=auth(alice)).json()})

tip = client.get(f"/projects/{fpid}/commits?branch=feature/x", headers=auth(alice)).json()[0]
check("commits are tagged with their branch and a files-changed count",
      tip["branch"] == "feature/x" and tip["files_changed"] == 1)
detail = client.get(f"/projects/{fpid}/commits/{tip['sha']}", headers=auth(alice)).json()
check("commit detail lists the changed file and names the parent",
      any(f["path"] == "l5x/line" for f in detail["files"]) and detail["parent"] is not None)
cs = client.get(f"/projects/{fpid}/commits/{tip['sha']}/diff/changeset?path=l5x/line",
                headers=auth(alice)).json()
check("per-commit changeset shows the modified rung",
      cs["programs"][0]["routines"][0]["rungs"][0]["kind"] == "modified")
root_sha = client.get(f"/projects/{fpid}/commits?branch=main", headers=auth(alice)).json()[0]["sha"]
root_detail = client.get(f"/projects/{fpid}/commits/{root_sha}", headers=auth(alice)).json()
check("the root commit diffs against the empty tree (all added)",
      root_detail["parent"] is None and root_detail["files"][0]["change"] == "added")

rel = client.post(f"/projects/{fpid}/tags",
                  json={"name": "v1.0.0", "ref": "main", "message": "First cut"},
                  headers=auth(erin))
check("a member can cut a release tag", rel.status_code == 201 and rel.json()["annotated"])
check("the release records its notes and tagger",
      rel.json()["message"] == "First cut" and rel.json()["tagger"] == "Erin Eve")
check("the tags card lists the release", [t["name"] for t in client.get(
      f"/projects/{fpid}/tags", headers=auth(alice)).json()] == ["v1.0.0"])
check("overview surfaces the latest release", client.get(
      f"/projects/{fpid}/overview", headers=auth(alice)).json()["latest_release"]["name"] == "v1.0.0")
check("a plain member cannot delete a release (manager only)", client.delete(
      f"/projects/{fpid}/tags/v1.0.0", headers=auth(erin)).status_code == 403)
check("the owner can delete a release", client.delete(
      f"/projects/{fpid}/tags/v1.0.0", headers=auth(alice)).status_code == 204)

print("== PR review workflow: protection, approvals, merge gate ==")
rpid = client.post("/projects", json={"name": "Review Demo"}, headers=auth(alice)).json()["id"]
client.post(f"/projects/{rpid}/members", json={"email": "bob@example.com"}, headers=auth(alice))
client.post(f"/projects/{rpid}/members", json={"email": "erin@example.com"}, headers=auth(alice))
commit(rpid, alice, "main", "Base", BASE)
client.post(f"/projects/{rpid}/branches", json={"name": "feature", "start_point": "main"}, headers=auth(alice))
commit(rpid, alice, "feature", "Add gate", CHANGE_X)

prot = client.put(f"/projects/{rpid}/branches/main/protection",
                  json={"protected": True, "required_approvals": 1}, headers=auth(alice))
check("default branch can carry a required-approvals count",
      prot.json()["is_protected"] and prot.json()["required_approvals"] == 1)

pr = client.post(f"/projects/{rpid}/pulls", json={
    "title": "Gate", "description": "Add a safety gate", "source_branch": "feature",
    "target_branch": "main"}, headers=auth(alice)).json()
check("PR created with a description and required_approvals from the branch",
      pr["description"] == "Add a safety gate" and pr["required_approvals"] == 1)
prn = pr["number"]
check("a member can edit the PR description", client.patch(
    f"/projects/{rpid}/pulls/{prn}", json={"description": "Add a safety gate (rev B)"},
    headers=auth(erin)).json()["description"] == "Add a safety gate (rev B)")

mg = client.get(f"/projects/{rpid}/pulls/{prn}/mergeability", headers=auth(alice)).json()
check("mergeability dry-run shows no conflicts before merge", mg["mergeable"] is True)
check("merge is gated until approvals are met",
      mg["approved"] is False and mg["can_merge"] is False)
check("merging without approvals is rejected (409)", client.post(
    f"/projects/{rpid}/pulls/{prn}/merge", headers=auth(alice)).status_code == 409)

appr = client.post(f"/projects/{rpid}/pulls/{prn}/approve", headers=auth(bob)).json()
check("an approval is recorded and counted", appr["approvals"] == 1 and appr["approved"] is True)
check("mergeability now allows merge", client.get(
    f"/projects/{rpid}/pulls/{prn}/mergeability", headers=auth(alice)).json()["can_merge"] is True)
check("merging after approval succeeds", client.post(
    f"/projects/{rpid}/pulls/{prn}/merge", headers=auth(alice)).json()["status"] == "merged")

print("== reviewers, threaded + anchored comments ==")
client.post(f"/projects/{rpid}/branches", json={"name": "feature2", "start_point": "main"}, headers=auth(alice))
commit(rpid, alice, "feature2", "More", CHANGE_Y)
prn2 = client.post(f"/projects/{rpid}/pulls", json={
    "title": "More", "source_branch": "feature2", "target_branch": "main"},
    headers=auth(alice)).json()["number"]
rv = client.post(f"/projects/{rpid}/pulls/{prn2}/reviewers",
                 json={"email": "bob@example.com"}, headers=auth(alice))
check("a reviewer can be invited", rv.status_code == 201 and any(
    r["email"] == "bob@example.com" for r in rv.json()["reviewers"]))
check("a non-member cannot be added as a reviewer", client.post(
    f"/projects/{rpid}/pulls/{prn2}/reviewers", json={"email": "carol@acme.com"},
    headers=auth(alice)).status_code == 400)

head_sha = client.get(f"/projects/{rpid}/commits?branch=feature2", headers=auth(alice)).json()[0]["sha"]
top = client.post(f"/projects/{rpid}/pulls/{prn2}/comments",
                  json={"body": "Overall looks good"}, headers=auth(alice)).json()
reply = client.post(f"/projects/{rpid}/pulls/{prn2}/comments",
                    json={"body": "Agreed", "parent_id": top["id"]}, headers=auth(bob)).json()
check("a reply is threaded under its parent", reply["parent_id"] == top["id"])
anchored = client.post(f"/projects/{rpid}/pulls/{prn2}/comments", json={
    "body": "Why change this rung?",
    "anchor": {"path": "l5x/line", "routine": "Main", "rung": 0, "sha": head_sha}},
    headers=auth(erin)).json()
check("a change-level comment keeps its anchor",
      anchored["anchor"]["path"] == "l5x/line" and anchored["anchor"]["routine"] == "Main")
clist = client.get(f"/projects/{rpid}/pulls/{prn2}/comments", headers=auth(alice))
check("comments list returns the whole thread with a total header",
      len(clist.json()) == 3 and clist.headers.get("X-Total-Count") == "3")
check("the author can edit their comment (edited_at set)", client.patch(
    f"/projects/{rpid}/pulls/{prn2}/comments/{top['id']}", json={"body": "Looks good!"},
    headers=auth(alice)).json()["edited_at"] is not None)
check("a non-author cannot edit a comment (403)", client.patch(
    f"/projects/{rpid}/pulls/{prn2}/comments/{top['id']}", json={"body": "hax"},
    headers=auth(bob)).status_code == 403)
check("the author can delete their comment (204)", client.delete(
    f"/projects/{rpid}/pulls/{prn2}/comments/{anchored['id']}", headers=auth(erin)).status_code == 204)
check("an open PR can be deleted by a manager", client.delete(
    f"/projects/{rpid}/pulls/{prn2}", headers=auth(alice)).status_code == 204)

print("== compare view model ==")
cmp_ = client.get(f"/projects/{rpid}/compare?base=main&head=feature2", headers=auth(alice))
check("compare reports rolled-up rung + file counts",
      cmp_.json()["summary"]["files_changed"] >= 1 and cmp_.json()["summary"]["rungs_modified"] >= 1)
check("compare lists affected symbols", any(
    "/" in s for s in cmp_.json()["affected_symbols"]))  # e.g. "MixerProg/Main"

print("== activity feed ==")
feed = client.get(f"/projects/{rpid}/activity", headers=auth(alice))
verbs = {e["verb"] for e in feed.json()}
check("activity feed records the key events",
      {"pull.opened", "pull.merged", "branch.created", "commit.pushed"} <= verbs)
check("activity feed is paginated with a total header",
      feed.headers.get("X-Total-Count") is not None)
check("a non-member cannot read the activity feed (403)",
      client.get(f"/projects/{rpid}/activity", headers=auth(carol)).status_code == 403)

print("== commit pagination header ==")
pg = client.get(f"/projects/{rpid}/commits?branch=main&limit=1", headers=auth(alice))
check("commit list reports the branch total via X-Total-Count",
      int(pg.headers.get("X-Total-Count", "0")) >= 2 and len(pg.json()) == 1)

print("== avatar, profile, password, org users ==")
prof = client.patch("/auth/me", json={"first_name": "Erin", "avatar": "147"}, headers=auth(erin))
check("profile avatar is updated", prof.json()["avatar"] == "147")
check("an invalid avatar code is rejected (400)", client.patch(
    "/auth/me", json={"avatar": "12"}, headers=auth(erin)).status_code == 400)
check("password change with the wrong current password is rejected (403)", client.post(
    "/auth/me/password", json={"current_password": "wrong", "new_password": "Brandnew12345"},
    headers=auth(erin)).status_code == 403)
check("password can be changed with the correct current password (204)", client.post(
    "/auth/me/password", json={"current_password": PW, "new_password": "Brandnew12345"},
    headers=auth(erin)).status_code == 204)
check("the new password works for login", client.post(
    "/auth/login", data={"username": "erin@example.com", "password": "Brandnew12345"}
).status_code == 200)
ou = client.get(f"/orgs/{acme_id}/users", headers=auth(alice))
check("org users list returns members with a total header",
      any(u["email"] == "alice@example.com" for u in ou.json())
      and ou.headers.get("X-Total-Count") is not None)

print("== org storage usage + 2 GB limit ==")
su = client.get("/storage", headers=auth(alice)).json()
check("storage usage reports used bytes and the 2 GB limit",
      su["limit_bytes"] == 2 * 1024 ** 3 and su["used_bytes"] > 0)
_saved_storage = settings.org_storage_limit_gb
settings.org_storage_limit_gb = 0.0  # any upload now exceeds the org quota
overq = commit(dpid, alice, "main", "Over quota", CHANGE_Y)
settings.org_storage_limit_gb = _saved_storage
check("an upload over the org storage limit is rejected (507)", overq.status_code == 507)

print("== delete project (cascade) ==")
delp = client.post("/projects", json={"name": "Trash"}, headers=auth(alice)).json()["id"]
commit(delp, alice, "main", "seed", BASE)
client.post(f"/projects/{delp}/branches", json={"name": "b", "start_point": "main"},
            headers=auth(alice))
commit(delp, alice, "b", "edit", CHANGE_X)
dprn = client.post(f"/projects/{delp}/pulls", json={
    "title": "x", "source_branch": "b", "target_branch": "main"},
    headers=auth(alice)).json()["number"]
client.post(f"/projects/{delp}/pulls/{dprn}/comments", json={"body": "x"}, headers=auth(alice))
_repo_path = settings.repos_dir / str(delp)
check("the project repo exists before delete", _repo_path.exists())
check("a non-member cannot delete", client.delete(
      f"/projects/{delp}", headers=auth(erin)).status_code == 403)
check("the owner can delete the project",
      client.delete(f"/projects/{delp}", headers=auth(alice)).status_code == 204)
check("the deleted project is gone (404)",
      client.get(f"/projects/{delp}", headers=auth(alice)).status_code == 404)
check("the repo directory was removed from disk", not _repo_path.exists())
_db3 = SessionLocal()
try:
    from sqlalchemy import func as _func, select as _select  # noqa: E402
    from app.models import PullRequest as _PR  # noqa: E402
    _remaining = _db3.scalar(
        _select(_func.count()).select_from(_PR).where(_PR.project_id == delp))
finally:
    _db3.close()
check("pull requests cascaded away on delete", _remaining == 0)

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

print("== invite rate limit ==")
rl_token = client.post(f"/orgs/{acme_id}/invites", json={"email": "rl@acme.com"},
                       headers=auth(alice)).json()["token"]
invite_burst = [
    client.get(f"/invites/{rl_token}").status_code
    for _ in range(settings.invite_rate_max + 5)
]
check("invite rate limit returns 429 after the cap", 429 in invite_burst)

print(f"\nALL {ok} CHECKS PASSED")
