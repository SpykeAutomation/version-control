"""Branch/commit/tag features layered on the Git-backed project repo:
ahead/behind, branch tips + delete, per-commit diff base, files-changed counts,
and tags (releases)."""
import pytest

from fixtures_l5x import KITCHEN_SINK
from vcs import ProjectRepo, ProjectRepoError, UploadSpec

CHANGE = KITCHEN_SINK.replace(
    "XIC(StartPB)OTE(RunLamp);", "XIC(StartPB)XIC(GateOk)OTE(RunLamp);"
)


def _l5x(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return UploadSpec(local_path=path, filename=name)


def _seeded(tmp_path):
    """A repo with one commit on main and a feature branch one commit ahead."""
    repo = ProjectRepo(tmp_path / "project")
    repo.init()
    repo.commit_files([_l5x(tmp_path, "line.L5X", KITCHEN_SINK)], branch="main",
                      title="Initial import")
    repo.create_branch("feature/gate", "main")
    repo.commit_files([_l5x(tmp_path, "line.L5X", CHANGE)], branch="feature/gate",
                      title="Add gate")
    return repo


def test_log_reports_files_changed_count(tmp_path):
    repo = _seeded(tmp_path)
    main_log = repo.log("main")
    assert main_log[0].files_changed == 1  # root commit: the one L5X file
    feat_log = repo.log("feature/gate", limit=1)
    assert feat_log[0].files_changed == 1  # the single modified L5X file


def test_ahead_behind_against_default(tmp_path):
    repo = _seeded(tmp_path)
    # feature/gate is one commit ahead of main, zero behind.
    assert repo.ahead_behind("feature/gate", "main") == (1, 0)
    # main has no commits feature lacks.
    assert repo.ahead_behind("main", "feature/gate") == (0, 1)


def test_ahead_behind_unresolvable_returns_none(tmp_path):
    repo = ProjectRepo(tmp_path / "project")
    repo.init()  # unborn main, no commits
    assert repo.ahead_behind("main", "nope") is None


def test_branch_tips_carry_latest_commit(tmp_path):
    repo = _seeded(tmp_path)
    tips = repo.branch_tips()
    assert set(tips) == {"main", "feature/gate"}
    assert tips["feature/gate"].title == "Add gate"
    assert tips["main"].sha == repo.resolve_ref("main")


def test_delete_branch_even_when_checked_out(tmp_path):
    repo = _seeded(tmp_path)
    # The last commit checked out feature/gate; deleting it must still work.
    assert repo.current_branch() == "feature/gate"
    repo.delete_branch("feature/gate", fallback="main")
    assert not repo.branch_exists("feature/gate")
    assert repo.current_branch() == "main"


def test_delete_unknown_branch_raises(tmp_path):
    repo = _seeded(tmp_path)
    with pytest.raises(ProjectRepoError, match="unknown branch"):
        repo.delete_branch("ghost")


def test_commit_diff_base_and_root_against_empty_tree(tmp_path):
    repo = _seeded(tmp_path)
    root = repo.resolve_ref("main")
    feat = repo.resolve_ref("feature/gate")
    # Root commit has no parent -> diffs against the empty tree.
    assert repo.commit_parent(root) is None
    assert repo.commit_diff_base(root) == ProjectRepo.EMPTY_TREE
    # The root's whole content shows as added against the empty tree.
    added = {f.path: f.change for f in repo.changed_files(ProjectRepo.EMPTY_TREE, root)}
    assert added == {"l5x/line": "added"}
    # A child commit diffs against its real parent.
    assert repo.commit_parent(feat) == root
    assert repo.commit_diff_base(feat) == root


def test_annotated_tag_is_a_release_with_notes(tmp_path):
    repo = _seeded(tmp_path)
    tag = repo.create_tag("v1.0.0", "main", message="First release",
                          tagger_name="Alice Anderson", tagger_email="alice@example.com")
    assert tag.annotated and tag.message == "First release"
    assert tag.tagger == "Alice Anderson"
    assert tag.target_sha == repo.resolve_ref("main")
    assert repo.tag_exists("v1.0.0")


def test_lightweight_tag_inherits_commit_date(tmp_path):
    repo = _seeded(tmp_path)
    tag = repo.create_tag("nightly", "feature/gate")  # no message -> lightweight
    assert not tag.annotated
    assert tag.message == ""
    assert tag.date  # falls back to the commit's date


def test_list_tags_is_newest_first_and_delete(tmp_path):
    repo = _seeded(tmp_path)
    repo.create_tag("v1", "main", message="one")
    repo.create_tag("v2", "feature/gate", message="two")
    names = [t.name for t in repo.list_tags()]
    assert names[0] == "v2" and set(names) == {"v1", "v2"}
    repo.delete_tag("v1")
    assert [t.name for t in repo.list_tags()] == ["v2"]


def test_create_tag_rejects_bad_name_and_duplicates(tmp_path):
    repo = _seeded(tmp_path)
    with pytest.raises(ProjectRepoError, match="invalid tag name"):
        repo.create_tag("-rf", "main")
    with pytest.raises(ProjectRepoError, match="invalid tag name"):
        repo.create_tag("bad..name", "main")
    repo.create_tag("v1", "main", message="x")
    with pytest.raises(ProjectRepoError, match="already exists"):
        repo.create_tag("v1", "main", message="y")


def test_merge_commit_files_changed_uses_first_parent(tmp_path):
    repo = _seeded(tmp_path)
    merge_sha = repo.merge("feature/gate", "main")
    log = repo.log("main", limit=1)
    assert log[0].sha == merge_sha
    # A clean merge that brought in the modified L5X reports it (not git's empty
    # default for merges) so the commit list agrees with the commit detail.
    assert log[0].files_changed == 1


def test_merge_preview_clean_does_not_touch_the_repo(tmp_path):
    repo = _seeded(tmp_path)
    before = repo.resolve_ref("main")
    mergeable, conflicts = repo.merge_preview("main", "feature/gate")
    assert mergeable is True and conflicts == []
    # The dry run must not advance main or change the checked-out branch.
    assert repo.resolve_ref("main") == before


def test_merge_preview_reports_conflicts(tmp_path):
    repo = ProjectRepo(tmp_path / "project")
    repo.init()
    repo.commit_files([_l5x(tmp_path, "line.L5X", KITCHEN_SINK)], branch="main",
                      title="Base")
    repo.create_branch("a", "main")
    repo.create_branch("b", "main")
    repo.commit_files([_l5x(tmp_path, "line.L5X", CHANGE)], branch="a", title="A")
    other = KITCHEN_SINK.replace(
        "XIC(StartPB)OTE(RunLamp);", "XIC(StartPB)XIC(EStop)OTE(RunLamp);"
    )
    repo.commit_files([_l5x(tmp_path, "line.L5X", other)], branch="b", title="B")
    repo.merge("a", "main")
    mergeable, conflicts = repo.merge_preview("main", "b")
    assert mergeable is False and conflicts  # the same routine changed both ways


def test_commit_count_and_total(tmp_path):
    repo = _seeded(tmp_path)
    assert repo.commit_total("main") == 1
    assert repo.commit_total("feature/gate") == 2
    assert repo.commit_count("main", "feature/gate") == 1  # one commit ahead
    assert repo.commit_count("feature/gate", "main") == 0


def test_log_offset_paginates(tmp_path):
    repo = ProjectRepo(tmp_path / "project")
    repo.init()
    for i in range(3):
        text = KITCHEN_SINK + f"\n<!-- {i} -->"
        repo.commit_files([_l5x(tmp_path, "line.L5X", text)], branch="main",
                          title=f"commit {i}")
    page1 = repo.log("main", limit=2, offset=0)
    page2 = repo.log("main", limit=2, offset=2)
    assert [c.title for c in page1] == ["commit 2", "commit 1"]
    assert [c.title for c in page2] == ["commit 0"]
