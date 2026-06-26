"""Git-backed project storage: uploads become per-file branch commits."""
import subprocess

import pytest

from fixtures_l5x import KITCHEN_SINK
from vcs import ProjectRepo, ProjectRepoError, UploadSpec


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _l5x(tmp_path, name, text):
    return UploadSpec(local_path=_write(tmp_path, name, text), filename=name)


def _file(tmp_path, name, text):
    return UploadSpec(local_path=_write(tmp_path, name, text), filename=name)


def test_l5x_commit_creates_namespaced_snapshot_and_raw(tmp_path):
    repo = ProjectRepo(tmp_path / "project")
    repo.init()

    first = repo.commit_files(
        [_l5x(tmp_path, "first.L5X", KITCHEN_SINK)],
        branch="main",
        title="Initial import",
        description="First L5X snapshot.",
    )

    assert first.branch == "main"
    assert first.sha == repo.resolve_ref("main")
    snap = repo.path / "l5x" / "first" / "snapshot"
    assert (snap / "controller.json").is_file()
    assert (snap / "programs" / "MixerProg" / "routines" / "Main.json").is_file()
    # The raw upload is kept beside the snapshot for exact-bytes download.
    assert (repo.path / "l5x" / "first" / "source.L5X").read_text() == KITCHEN_SINK


def test_branch_commit_and_per_file_diff(tmp_path):
    repo = ProjectRepo(tmp_path / "project")
    repo.init()
    repo.commit_files(
        [_l5x(tmp_path, "line.L5X", KITCHEN_SINK)], branch="main", title="Initial import"
    )

    repo.create_branch("feature/start-gate", "main")
    changed = KITCHEN_SINK.replace(
        "XIC(StartPB)OTE(RunLamp);",
        "XIC(StartPB)XIC(GateOk)OTE(RunLamp);",
    )
    # Same filename -> versions the same logical file.
    repo.commit_files(
        [_l5x(tmp_path, "line.L5X", changed)],
        branch="feature/start-gate",
        title="Add gate permissive",
    )

    changes = repo.diff_refs("main", "feature/start-gate", "line")
    assert [p.name for p in changes.programs] == ["MixerProg"]
    routine = changes.programs[0].routines[0]
    assert routine.name == "Main"
    assert routine.rungs[0].kind == "modified"


def test_multi_file_commit_manifest_and_text_diff(tmp_path):
    repo = ProjectRepo(tmp_path / "project")
    repo.init()
    repo.commit_files(
        [
            _l5x(tmp_path, "lineA.L5X", KITCHEN_SINK),
            _l5x(tmp_path, "lineB.L5X", KITCHEN_SINK),
            _file(tmp_path, "bom.csv", "part,qty\nA,1\n"),
        ],
        branch="main",
        title="Import two lines + BOM",
    )

    repo.create_branch("edit", "main")
    changed = KITCHEN_SINK.replace(
        "XIC(StartPB)OTE(RunLamp);", "XIC(StartPB)XIC(GateOk)OTE(RunLamp);"
    )
    repo.commit_files(
        [
            _l5x(tmp_path, "lineA.L5X", changed),
            _file(tmp_path, "bom.csv", "part,qty\nA,2\nB,5\n"),
        ],
        branch="edit",
        title="Tweak line A + BOM",
    )

    manifest = {f.path: f for f in repo.changed_files("main", "edit")}
    assert manifest["l5x/lineA"].change == "modified"
    assert manifest["files/bom.csv"].change == "modified"
    assert "l5x/lineB" not in manifest  # unchanged file is not listed

    binary, unified = repo.text_file_diff("main", "edit", "files/bom.csv")
    assert binary is False
    assert "B,5" in unified


def test_added_file_diffs_against_empty(tmp_path):
    repo = ProjectRepo(tmp_path / "project")
    repo.init()
    repo.commit_files(
        [_l5x(tmp_path, "lineA.L5X", KITCHEN_SINK)], branch="main", title="A only"
    )
    repo.create_branch("more", "main")
    repo.commit_files(
        [_l5x(tmp_path, "lineB.L5X", KITCHEN_SINK)], branch="more", title="Add B"
    )

    manifest = {f.path: f.change for f in repo.changed_files("main", "more")}
    assert manifest == {"l5x/lineB": "added"}
    # A changeset for the added file shows its content as added, no crash.
    added = repo.diff_refs("main", "more", "lineB")
    assert [p.name for p in added.programs] == ["MixerProg"]


def test_raw_blob_round_trips_at_old_ref(tmp_path):
    repo = ProjectRepo(tmp_path / "project")
    repo.init()
    repo.commit_files(
        [_l5x(tmp_path, "line.L5X", KITCHEN_SINK)], branch="main", title="v1"
    )
    repo.create_branch("v2", "main")
    repo.commit_files(
        [_l5x(tmp_path, "line.L5X", KITCHEN_SINK + "\n")], branch="v2", title="v2"
    )

    assert repo.read_blob("main", "l5x/line/source.L5X").decode() == KITCHEN_SINK
    assert repo.read_blob("v2", "l5x/line/source.L5X").decode() == KITCHEN_SINK + "\n"


def test_batch_with_bad_l5x_is_rejected_atomically(tmp_path):
    repo = ProjectRepo(tmp_path / "project")
    repo.init()

    with pytest.raises(ProjectRepoError, match="could not parse L5X file"):
        repo.commit_files(
            [
                _l5x(tmp_path, "good.L5X", KITCHEN_SINK),
                _l5x(tmp_path, "bad.L5X", "<not an l5x/>"),
            ],
            branch="main",
            title="Bad batch",
        )

    # Nothing was written: the good file's folder must not exist.
    assert not (repo.path / "l5x" / "good").exists()


def test_unchanged_upload_is_not_committed(tmp_path):
    repo = ProjectRepo(tmp_path / "project")
    repo.init()
    spec = _l5x(tmp_path, "project.L5X", KITCHEN_SINK)
    repo.commit_files([spec], branch="main", title="Initial import")

    with pytest.raises(ProjectRepoError, match="no changes"):
        repo.commit_files([spec], branch="main", title="No-op import")


def test_missing_git_repo_is_rejected(tmp_path):
    repo = ProjectRepo(tmp_path / "not-created")

    with pytest.raises(ProjectRepoError, match="not a Git project repo"):
        repo.resolve_ref("HEAD")


def test_init_is_idempotent(tmp_path):
    repo = ProjectRepo(tmp_path / "project")
    repo.init()
    first_git_dir = subprocess.run(
        ["git", "-C", str(repo.path), "rev-parse", "--git-dir"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    repo.init()

    assert first_git_dir == ".git"
