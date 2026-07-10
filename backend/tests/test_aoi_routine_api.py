"""API tests for the AOI scope of GET /projects/{id}/commits/{sha}/routine —
AOI routines rendered through the same ladder-IR pipeline as program routines
(exactly one of program/aoi selects the scope; encoded AOIs and FBD/SFC 404)."""
import os
import tempfile

# Point the app at a throwaway data dir BEFORE any app module is imported —
# app.config builds its settings singleton (SQLite path, repos dir) at import.
# When another API test module imported first, its data dir simply wins.
os.environ["PLCVC_DATA_DIR"] = tempfile.mkdtemp(prefix="plcvc-aoi-routine-api-")

import pytest

# The engine-only environment (requirements-dev.txt: parser + diff deps) has no
# app stack; these API tests need it (requirements-app.txt). CI runs them in
# the api-tests job; the engine matrix skips this module instead of failing.
pytest.importorskip("fastapi", reason="API tests need requirements-app.txt")

from fastapi.testclient import TestClient

from app.auth import create_user
from app.db import SessionLocal
from app.main import app
from fixtures_l5x import KITCHEN_SINK

# Satisfies the password policy: >=12 chars with upper + lower + digit.
PW = "Abcdef123456"

# KITCHEN_SINK's ValveCtl AOI has a single NOP() Logic routine. Give it a
# drawable rung (contact -> coil over its parameter/local tag), an ST Prescan,
# and an FBD routine, so every AOI-scope content path is exercised.
AOI_ROUTINES = KITCHEN_SINK.replace(
    "<Routines>"
    '<Routine Name="Logic" Type="RLL">'
    '<RLLContent><Rung Number="0"><Text>NOP();</Text></Rung></RLLContent>'
    "</Routine></Routines>",
    "<Routines>"
    '<Routine Name="Logic" Type="RLL">'
    '<RLLContent><Rung Number="0"><Comment>travel</Comment>'
    "<Text>XIC(OpenTime)OTE(TravelTmr.EN);</Text></Rung></RLLContent>"
    "</Routine>"
    '<Routine Name="Prescan" Type="ST">'
    '<STContent><Line Number="0"><Text>TravelTmr.PRE := 100;</Text></Line></STContent>'
    "</Routine>"
    '<Routine Name="Blend" Type="FBD">'
    '<FBDContent SheetSize="Letter"><Sheet Number="1"/></FBDContent></Routine>'
    "</Routines>",
)
assert AOI_ROUTINES != KITCHEN_SINK, "fixture anchor no longer matches"


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
    """One project with the AOI-routines L5X on main, plus an outsider."""

    def __init__(self, client: TestClient) -> None:
        self.owner = _login(client, "aoi-routine-owner@example.com", "Ada", "Owner")
        self.outsider = _login(client, "aoi-routine-outsider@example.com", "Out", "Sider")
        self.pid = client.post(
            "/projects", json={"name": "AOI Routine Reads"}, headers=_auth(self.owner)
        ).json()["id"]
        r = client.post(
            f"/projects/{self.pid}/commits",
            files=[("files", ("line.L5X", AOI_ROUTINES, "application/octet-stream"))],
            data={"branch": "main", "title": "Initial import"},
            headers=_auth(self.owner),
        )
        assert r.status_code == 201, r.text
        self.sha = r.json()["sha"]


@pytest.fixture(scope="module")
def seed(client: TestClient) -> Seed:
    return Seed(client)


def _get(client, seed, *, routine, program=None, aoi=None, token=None, path=None):
    params = {"routine": routine}
    if program is not None:
        params["program"] = program
    if aoi is not None:
        params["aoi"] = aoi
    if path is not None:
        params["path"] = path
    return client.get(
        f"/projects/{seed.pid}/commits/{seed.sha}/routine",
        params=params,
        headers=_auth(token or seed.owner),
    )


def test_rll_aoi_routine_returns_ladder_ir(client, seed):
    r = _get(client, seed, aoi="ValveCtl", routine="Logic")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "ladder"
    ladder = body["ladder"]
    # The AOI name fills the IR's program field so the header reads sensibly.
    assert ladder["program"] == "ValveCtl" and ladder["routine"] == "Logic"
    assert ladder["routine_type"] == "RLL"
    assert ladder["controller"] == "ctrllr"
    assert ladder["new_label"] == seed.sha[:7]
    assert ladder["rungs"], "the routine's rungs must be present"
    for rung in ladder["rungs"]:
        assert rung["status"] == "unchanged"
        assert rung["before"] == []
    first = ladder["rungs"][0]
    assert first["new_number"] == 0 and first["new_comment"] == "travel"
    # Parameter / local-tag operands render as plain contact/coil labels.
    assert [el["kind"] for el in first["after"]] == ["contact", "coil"]
    assert [el["label"] for el in first["after"]] == ["OpenTime", "TravelTmr.EN"]


def test_st_aoi_routine_returns_numbered_lines(client, seed):
    r = _get(client, seed, aoi="ValveCtl", routine="Prescan")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "structured"
    assert body["ref"] == seed.sha[:7]
    assert body["lines"] == [{"ln": 1, "text": "TravelTmr.PRE := 100;"}]


def test_fbd_aoi_routine_is_404(client, seed):
    r = _get(client, seed, aoi="ValveCtl", routine="Blend")
    assert r.status_code == 404
    assert "not available" in r.json()["detail"]


def test_exactly_one_scope_is_required(client, seed):
    both = _get(client, seed, program="MixerProg", aoi="ValveCtl", routine="Logic")
    assert both.status_code == 400
    assert "program or aoi" in both.json()["detail"]
    neither = _get(client, seed, routine="Logic")
    assert neither.status_code == 400
    assert "program or aoi" in neither.json()["detail"]


def test_unknown_aoi_or_routine_is_404(client, seed):
    assert _get(client, seed, aoi="Ghost", routine="Logic").status_code == 404
    assert _get(client, seed, aoi="ValveCtl", routine="Ghost").status_code == 404


def test_encoded_aoi_is_404(client, seed):
    r = _get(client, seed, aoi="ProtValveCtl", routine="Logic")
    assert r.status_code == 404
    assert "source-protected" in r.json()["detail"]


def test_explicit_l5x_path_pins_the_file(client, seed):
    assert _get(client, seed, aoi="ValveCtl", routine="Logic", path="l5x/line").status_code == 200
    assert _get(client, seed, aoi="ValveCtl", routine="Logic", path="l5x/ghost").status_code == 404


def test_program_scope_behaves_as_before(client, seed):
    r = _get(client, seed, program="MixerProg", routine="Main")
    assert r.status_code == 200, r.text
    ladder = r.json()["ladder"]
    assert ladder["program"] == "MixerProg" and ladder["routine"] == "Main"
    assert [el["kind"] for el in ladder["rungs"][0]["after"]] == ["contact", "coil"]


def test_non_member_is_403(client, seed):
    r = _get(client, seed, aoi="ValveCtl", routine="Logic", token=seed.outsider)
    assert r.status_code == 403
