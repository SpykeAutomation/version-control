"""Single-commit diff routes: what one commit changed against its parent.

These exercise the two endpoints added to the projects router:
  GET /projects/{id}/commits/{sha}/diff         -> ChangeSet
  GET /projects/{id}/commits/{sha}/diff/ladder  -> LadderDocument

Auth and the database are stubbed out (the membership check is replaced with a
no-op), so the tests focus on the diff behaviour. Each test points the app at a
throwaway Git repo built from the shared L5X fixture.
"""
import pytest
from fastapi.testclient import TestClient

from fixtures_l5x import KITCHEN_SINK
from vcs import ProjectRepo

from app.auth import current_user
from app.config import settings
from app.db import get_db
from app.main import app
from app.routers import projects

PROJECT_ID = 1


def _write_l5x(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient wired to a tmp data dir, with auth/membership stubbed.

    `repo_for` and the diff cache both read `settings.data_dir` at call time,
    so pointing it at tmp_path isolates each test. The membership check needs a
    real database; here it is replaced with a no-op so no DB is required.
    """
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(projects, "require_member", lambda pid, db, user: None)
    app.dependency_overrides[current_user] = lambda: None
    app.dependency_overrides[get_db] = lambda: None
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _repo(tmp_path):
    return ProjectRepo(settings.repos_dir / str(PROJECT_ID))


def _commit(repo, tmp_path, name, text, *, title):
    return repo.commit_l5x(
        _write_l5x(tmp_path, name, text), branch="main", title=title
    )


def test_non_root_commit_diffs_against_its_parent(client, tmp_path):
    repo = _repo(tmp_path)
    repo.init()
    _commit(repo, tmp_path, "base.L5X", KITCHEN_SINK, title="Initial import")

    changed = KITCHEN_SINK.replace(
        "XIC(StartPB)OTE(RunLamp);",
        "XIC(StartPB)XIC(GateOk)OTE(RunLamp);",
    )
    head = _commit(repo, tmp_path, "changed.L5X", changed, title="Add gate permissive")

    resp = client.get(f"/projects/{PROJECT_ID}/commits/{head.sha}/diff")
    assert resp.status_code == 200
    body = resp.json()

    # Only the one routine that actually changed should appear.
    assert [p["name"] for p in body["programs"]] == ["MixerProg"]
    routine = body["programs"][0]["routines"][0]
    assert routine["name"] == "Main"
    assert routine["rungs"][0]["kind"] == "modified"
    # The controller/metadata did not change between the two commits.
    assert body["controller"] == []


def test_root_commit_diff_reads_as_all_added(client, tmp_path):
    repo = _repo(tmp_path)
    repo.init()
    root = _commit(repo, tmp_path, "first.L5X", KITCHEN_SINK, title="Initial import")

    resp = client.get(f"/projects/{PROJECT_ID}/commits/{root.sha}/diff")
    assert resp.status_code == 200
    body = resp.json()

    # The first commit has no parent, so every entity reads as added and there
    # are no spurious controller/metadata field changes.
    assert body["controller"] == []
    assert body["programs"], "expected the root commit to add programs"
    assert all(p["kind"] == "added" for p in body["programs"])
    assert all(m["kind"] == "added" for m in body["modules"])
    assert all(t["kind"] == "added" for t in body["data_types"])


def test_non_root_ladder_diff_shape(client, tmp_path):
    repo = _repo(tmp_path)
    repo.init()
    _commit(repo, tmp_path, "base.L5X", KITCHEN_SINK, title="Initial import")
    changed = KITCHEN_SINK.replace(
        "XIC(StartPB)OTE(RunLamp);",
        "XIC(StartPB)XIC(GateOk)OTE(RunLamp);",
    )
    head = _commit(repo, tmp_path, "changed.L5X", changed, title="Add gate permissive")

    resp = client.get(f"/projects/{PROJECT_ID}/commits/{head.sha}/diff/ladder")
    assert resp.status_code == 200
    body = resp.json()

    assert body["commit"] == head.sha
    assert [r["routine"] for r in body["routines"]] == ["Main"]
    card = body["routines"][0]
    # Labels are the short shas of the parent and the commit.
    assert card["new_label"] == head.sha[:7]
    assert len(card["old_label"]) == 7


def test_root_ladder_diff_shape(client, tmp_path):
    repo = _repo(tmp_path)
    repo.init()
    root = _commit(repo, tmp_path, "first.L5X", KITCHEN_SINK, title="Initial import")

    resp = client.get(f"/projects/{PROJECT_ID}/commits/{root.sha}/diff/ladder")
    assert resp.status_code == 200
    body = resp.json()

    # The ladder view draws routines side-by-side, so it only has cards for
    # routines that exist on both sides. A root commit has no "before", so the
    # document is well-formed but carries no cards — the per-routine "added"
    # detail lives in the changeset view, not here.
    assert body["commit"] == root.sha
    assert body["routines"] == []


def test_commit_ladder_diff_does_not_collide_with_generic_ladder_cache(client, tmp_path):
    repo = _repo(tmp_path)
    repo.init()
    _commit(repo, tmp_path, "base.L5X", KITCHEN_SINK, title="Initial import")
    changed = KITCHEN_SINK.replace(
        "XIC(StartPB)OTE(RunLamp);",
        "XIC(StartPB)XIC(GateOk)OTE(RunLamp);",
    )
    head = _commit(repo, tmp_path, "changed.L5X", changed, title="Add gate permissive")

    # Prime the generic ref-to-ref ladder cache for the SAME commit pair; it
    # stores ref-name labels ("main"), not short shas.
    generic = client.get(
        f"/projects/{PROJECT_ID}/diff/ladder",
        params={"base": "main~1", "head": "main"},
    )
    assert generic.status_code == 200
    assert generic.json()["routines"][0]["new_label"] == "main"

    # The single-commit endpoint must return its own short-sha labels rather
    # than serve the generic endpoint's cached "main" label — i.e. the two
    # views must not share a cache namespace.
    resp = client.get(f"/projects/{PROJECT_ID}/commits/{head.sha}/diff/ladder")
    assert resp.status_code == 200
    assert resp.json()["routines"][0]["new_label"] == head.sha[:7]


def test_bad_sha_is_a_clean_client_error(client, tmp_path):
    repo = _repo(tmp_path)
    repo.init()
    _commit(repo, tmp_path, "first.L5X", KITCHEN_SINK, title="Initial import")

    resp = client.get(f"/projects/{PROJECT_ID}/commits/deadbeef/diff")
    assert resp.status_code == 400
