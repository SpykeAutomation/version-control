"""API tests for GET /projects/{id}/l5x — raw sections of a parsed L5X file
at a ref (controller / datatypes / tags / modules / one AOI), served through
the sha-keyed diff cache, with the measured-heavy per-entity fields excluded
from the list sections."""
import os
import tempfile

# Point the app at a throwaway data dir BEFORE any app module is imported —
# app.config builds its settings singleton (SQLite path, repos dir) at import.
# When another API test module imported first, its data dir simply wins.
os.environ["PLCVC_DATA_DIR"] = tempfile.mkdtemp(prefix="plcvc-sections-api-")

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
    """One project with the kitchen-sink L5X on main, plus an outsider."""

    def __init__(self, client: TestClient) -> None:
        self.owner = _login(client, "sections-owner@example.com", "Sec", "Owner")
        self.outsider = _login(client, "sections-outsider@example.com", "Out", "Sider")
        self.pid = client.post(
            "/projects", json={"name": "Section Reads"}, headers=_auth(self.owner)
        ).json()["id"]
        r = client.post(
            f"/projects/{self.pid}/commits",
            files=[("files", ("line.L5X", KITCHEN_SINK, "application/octet-stream"))],
            data={"branch": "main", "title": "Initial import"},
            headers=_auth(self.owner),
        )
        assert r.status_code == 201, r.text


@pytest.fixture(scope="module")
def seed(client: TestClient) -> Seed:
    return Seed(client)


def _get(client, seed, section, *, token=None, ref="main", path="l5x/line", name=None):
    params = {"ref": ref, "path": path, "section": section}
    if name is not None:
        params["name"] = name
    return client.get(
        f"/projects/{seed.pid}/l5x", params=params, headers=_auth(token or seed.owner)
    )


# First test in the file so no earlier test has warmed this cache key.
def test_second_request_is_a_cache_hit(client, seed):
    r1 = _get(client, seed, "controller")
    assert r1.status_code == 200, r1.text
    assert r1.headers.get("X-Cache") == "MISS"
    r2 = _get(client, seed, "controller")
    assert r2.headers.get("X-Cache") == "HIT"
    assert r2.json() == r1.json()


def test_controller_section(client, seed):
    body = _get(client, seed, "controller").json()
    assert body["schema_version"] == 1
    assert body["section"] == "controller"
    data = body["data"]
    assert data["name"] == "ctrllr"
    assert data["processor_type"] == "1756-L85E"
    assert data["fault_handler_program"] == "FaultHandler"


def test_datatypes_section_includes_members(client, seed):
    body = _get(client, seed, "datatypes").json()
    assert body["section"] == "datatypes"
    by_name = {d["name"]: d for d in body["data"]}
    assert "DemoUDT" in by_name
    members = {m["name"] for m in by_name["DemoUDT"]["members"]}
    assert {"Setpoints", "RunFlag"} <= members


def test_tags_section_excludes_heavy_fields(client, seed):
    body = _get(client, seed, "tags").json()
    rows = body["data"]
    names = {t["name"] for t in rows}
    # MixerState carries values, ReadMsg carries message_config — both stay
    # listed, but the heavy per-tag blobs are excluded from the grid payload.
    assert {"CycleCount", "MixerState", "ReadMsg", "StartPB"} <= names
    for row in rows:
        assert "values" not in row
        assert "comments" not in row
        assert "message_config" not in row
    by_name = {t["name"]: t for t in rows}
    assert by_name["CycleCount"]["value"] == "5"  # scalar value stays
    assert by_name["StartPB"]["alias_for"] == "LocalIn.3"


def test_modules_section_excludes_heavy_fields(client, seed):
    body = _get(client, seed, "modules").json()
    rows = body["data"]
    assert [m["name"] for m in rows] == ["EnetAdapter"]
    row = rows[0]
    assert row["catalog_number"] == "1756-EN2TR"
    for heavy in ("config_values", "connections", "rack_connections", "extended_properties"):
        assert heavy not in row


def test_aoi_section_returns_one_full_definition(client, seed):
    body = _get(client, seed, "aoi", name="ValveCtl").json()
    assert body["section"] == "aoi"
    data = body["data"]
    assert data["name"] == "ValveCtl"
    params = {p["name"]: p for p in data["parameters"]}
    assert params["OpenTime"]["required"] is True
    assert [t["name"] for t in data["local_tags"]] == ["TravelTmr"]
    routines = {r["name"]: r for r in data["routines"]}
    assert routines["Logic"]["content"]["rungs"][0]["text"] == "NOP();"


def test_aoi_requires_name(client, seed):
    r = _get(client, seed, "aoi")
    assert r.status_code == 400
    assert "name" in r.json()["detail"]


def test_unknown_aoi_is_400(client, seed):
    assert _get(client, seed, "aoi", name="Ghost").status_code == 400


def test_unknown_section_is_422(client, seed):
    assert _get(client, seed, "organizer").status_code == 422


def test_missing_file_or_ref_is_400(client, seed):
    assert _get(client, seed, "controller", path="l5x/ghost").status_code == 400
    assert _get(client, seed, "controller", ref="no-such-ref").status_code == 400


def test_non_member_is_403(client, seed):
    assert _get(client, seed, "controller", token=seed.outsider).status_code == 403
