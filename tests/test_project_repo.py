"""Git-backed project storage: L5X upload becomes branch commits."""
import subprocess

import pytest

from fixtures_l5x import KITCHEN_SINK
from vcs import ProjectRepo, ProjectRepoError


def _write_l5x(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_l5x_commit_creates_snapshot_files(tmp_path):
    repo = ProjectRepo(tmp_path / "project")
    repo.init()

    first = repo.commit_l5x(
        _write_l5x(tmp_path, "first.L5X", KITCHEN_SINK),
        branch="main",
        title="Initial import",
        description="First L5X snapshot.",
    )

    assert first.branch == "main"
    assert first.sha == repo.resolve_ref("main")
    assert (repo.path / "controller.json").is_file()
    assert (repo.path / "programs" / "MixerProg" / "routines" / "Main.json").is_file()


def test_branch_commit_and_diff_refs(tmp_path):
    repo = ProjectRepo(tmp_path / "project")
    repo.init()
    base_l5x = _write_l5x(tmp_path, "base.L5X", KITCHEN_SINK)
    repo.commit_l5x(base_l5x, branch="main", title="Initial import")

    repo.create_branch("feature/start-gate", "main")
    changed = KITCHEN_SINK.replace(
        "XIC(StartPB)OTE(RunLamp);",
        "XIC(StartPB)XIC(GateOk)OTE(RunLamp);",
    )
    repo.commit_l5x(
        _write_l5x(tmp_path, "changed.L5X", changed),
        branch="feature/start-gate",
        title="Add gate permissive",
    )

    changes = repo.diff_refs("main", "feature/start-gate")
    assert [p.name for p in changes.programs] == ["MixerProg"]
    routine = changes.programs[0].routines[0]
    assert routine.name == "Main"
    assert routine.rungs[0].kind == "modified"


def test_unchanged_l5x_is_not_committed(tmp_path):
    repo = ProjectRepo(tmp_path / "project")
    repo.init()
    l5x = _write_l5x(tmp_path, "project.L5X", KITCHEN_SINK)
    repo.commit_l5x(l5x, branch="main", title="Initial import")

    with pytest.raises(ProjectRepoError, match="no snapshot changes"):
        repo.commit_l5x(l5x, branch="main", title="No-op import")


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
