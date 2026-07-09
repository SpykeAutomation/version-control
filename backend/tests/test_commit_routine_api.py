"""API tests for GET /projects/{id}/commits/{sha}/routine — the full,
read-only content of one routine as committed (ladder IR for RLL, numbered
lines for ST, 404 for encoded/FBD/SFC, member-gated like the sibling
commit reads)."""
import os
import tempfile

# Point the app at a throwaway data dir BEFORE any app module is imported —
# app.config builds its settings singleton (SQLite path, repos dir) at import.
os.environ["PLCVC_DATA_DIR"] = tempfile.mkdtemp(prefix="plcvc-routine-api-")

import pytest

# The engine-only environment (requirements-dev.txt: parser + diff deps) has no
# app stack; these API tests need it (requirements-app.txt). CI runs them in
# the dedicated api-tests job on the app's deployment Python; the engine
# matrix (3.10/3.14, Windows) skips this module instead of failing collection.
pytest.importorskip("fastapi", reason="API tests need requirements-app.txt")

from fastapi.testclient import TestClient

from app.auth import create_user
from app.db import SessionLocal
from app.main import app
from fixtures_l5x import KITCHEN_SINK

# Satisfies the password policy: >=12 chars with upper + lower + digit.
PW = "Abcdef123456"

# A second revision of Main: rung 0 calls the ValveCtl AOI (so operand labels
# come from the snapshot's AOI definitions) and rung 1 is text the RLL grammar
# cannot read (so the raw fallback renders instead of failing the routine).
AOI_CALL = KITCHEN_SINK.replace(
    "<Text>XIC(StartPB)OTE(RunLamp);</Text></Rung>",
    "<Text>XIC(StartPB)ValveCtl(V1,10)OTE(RunLamp);</Text></Rung>"
    '<Rung Number="1"><Text>%%not ladder logic%%</Text></Rung>',
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
    """One project with two commits of the kitchen-sink L5X, plus an outsider."""

    def __init__(self, client: TestClient) -> None:
        self.owner = _login(client, "routine-owner@example.com", "Rae", "Owner")
        self.outsider = _login(client, "routine-outsider@example.com", "Out", "Sider")
        self.pid = client.post(
            "/projects", json={"name": "Routine Reads"}, headers=_auth(self.owner)
        ).json()["id"]
        self.sha = self._commit(client, "Initial import", KITCHEN_SINK)
        self.aoi_sha = self._commit(client, "Call the valve AOI", AOI_CALL)

    def _commit(self, client: TestClient, title: str, text: str) -> str:
        r = client.post(
            f"/projects/{self.pid}/commits",
            files=[("files", ("line.L5X", text, "application/octet-stream"))],
            data={"branch": "main", "title": title},
            headers=_auth(self.owner),
        )
        assert r.status_code == 201, r.text
        return r.json()["sha"]


@pytest.fixture(scope="module")
def seed(client: TestClient) -> Seed:
    return Seed(client)


def _get(client, seed, program, routine, *, token=None, sha=None, path=None):
    params = {"program": program, "routine": routine}
    if path is not None:
        params["path"] = path
    return client.get(
        f"/projects/{seed.pid}/commits/{sha or seed.sha}/routine",
        params=params,
        headers=_auth(token or seed.owner),
    )


def test_ladder_routine_returns_full_unchanged_content(client, seed):
    r = _get(client, seed, "MixerProg", "Main")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "ladder"
    ladder = body["ladder"]
    assert ladder["program"] == "MixerProg" and ladder["routine"] == "Main"
    assert ladder["routine_type"] == "RLL"
    assert ladder["controller"] == "ctrllr"
    assert ladder["new_label"] == seed.sha[:7]
    assert ladder["summary"] == {
        "rungs_modified": 0, "rungs_added": 0, "rungs_removed": 0,
        "additions": 0, "removals": 0,
    }
    assert ladder["rungs"], "the routine's rungs must be present"
    for rung in ladder["rungs"]:
        assert rung["status"] == "unchanged"
        assert rung["before"] == []
        assert rung["after"], "full content draws on the after side"
    first = ladder["rungs"][0]
    assert first["new_number"] == 0
    assert first["new_comment"] == "start gate"
    # XIC(StartPB) OTE(RunLamp) -> a contact then a coil.
    assert [el["kind"] for el in first["after"]] == ["contact", "coil"]
    assert [el["label"] for el in first["after"]] == ["StartPB", "RunLamp"]


def test_explicit_l5x_path_pins_the_file(client, seed):
    r = _get(client, seed, "MixerProg", "Main", path="l5x/line")
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == "ladder"
    # A path that exists but holds no such file is a 404, not an error.
    assert _get(client, seed, "MixerProg", "Main", path="l5x/ghost").status_code == 404


def test_aoi_operand_labels_and_raw_fallback(client, seed):
    ladder = _get(client, seed, "MixerProg", "Main", sha=seed.aoi_sha).json()["ladder"]
    assert ladder["new_label"] == seed.aoi_sha[:7]
    box = next(el for el in ladder["rungs"][0]["after"] if el["kind"] == "box")
    assert box["mnemonic"] == "ValveCtl"
    # Backing tag unlabeled, then the AOI's required parameter by name.
    assert [(op["label"], op["value"]) for op in box["operands"]] == [
        ("", "V1"), ("OpenTime", "10"),
    ]
    # The unparseable rung renders verbatim instead of failing the request.
    bad = ladder["rungs"][1]
    assert bad["status"] == "unchanged"
    assert [el["kind"] for el in bad["after"]] == ["raw"]
    assert bad["after"][0]["text"] == "%%not ladder logic%%"


def test_st_routine_returns_numbered_lines(client, seed):
    r = _get(client, seed, "MixerProg", "Calc")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "structured"
    assert body["ref"] == seed.sha[:7]
    assert body["lines"] == [{"ln": 1, "text": "StepNo := 1;"}]


def test_unknown_routine_program_or_sha_is_404(client, seed):
    assert _get(client, seed, "MixerProg", "Ghost").status_code == 404
    assert _get(client, seed, "GhostProg", "Main").status_code == 404
    assert _get(client, seed, "MixerProg", "Main", sha="0" * 40).status_code == 404
    assert _get(client, seed, "MixerProg", "Main", sha="not-a-ref").status_code == 404


def test_unparsed_content_types_are_404(client, seed):
    fbd = _get(client, seed, "MixerProg", "Blend")  # FBD: no parsed content
    assert fbd.status_code == 404
    assert "not available" in fbd.json()["detail"]
    prot = _get(client, seed, "MixerProg", "ProtCalc")  # encoded (source-protected)
    assert prot.status_code == 404
    assert "not available" in prot.json()["detail"]


def test_non_member_is_403(client, seed):
    r = _get(client, seed, "MixerProg", "Main", token=seed.outsider)
    assert r.status_code == 403
