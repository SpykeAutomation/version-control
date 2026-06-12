"""CLI behavior: exit codes, JSON output, mixed input kinds."""
import json

from diff.__main__ import main
from diff.models import ChangeSet
from snapshot import write_snapshot

from fixtures_l5x import KITCHEN_SINK


def _changed_xml():
    changed = KITCHEN_SINK.replace(
        "XIC(StartPB)OTE(RunLamp);", "XIC(StartPB)XIC(GateOk)OTE(RunLamp);"
    )
    assert changed != KITCHEN_SINK
    return changed


def test_identical_snapshots_exit_0(tmp_path, l5x, capsys):
    doc = l5x.parse_string(KITCHEN_SINK)
    write_snapshot(doc, tmp_path / "a")
    write_snapshot(doc, tmp_path / "b")
    assert main([str(tmp_path / "a"), str(tmp_path / "b")]) == 0
    assert "No differences found." in capsys.readouterr().out


def test_differences_exit_1_and_read_plainly(tmp_path, l5x, capsys):
    write_snapshot(l5x.parse_string(KITCHEN_SINK), tmp_path / "a")
    write_snapshot(l5x.parse_string(_changed_xml()), tmp_path / "b")
    assert main([str(tmp_path / "a"), str(tmp_path / "b")]) == 1
    out = capsys.readouterr().out
    assert "Program MixerProg" in out
    assert "rung 0 changed" in out


def test_missing_input_exit_2(tmp_path, capsys):
    assert main([str(tmp_path / "missing"), str(tmp_path / "also_missing")]) == 2
    assert "error:" in capsys.readouterr().err


def test_json_output_parses_back(tmp_path, l5x, capsys):
    write_snapshot(l5x.parse_string(KITCHEN_SINK), tmp_path / "a")
    write_snapshot(l5x.parse_string(_changed_xml()), tmp_path / "b")
    assert main([str(tmp_path / "a"), str(tmp_path / "b"), "--json"]) == 1
    cs = ChangeSet.model_validate(json.loads(capsys.readouterr().out))
    assert not cs.is_empty()


def test_l5x_file_vs_snapshot_folder_exit_0(tmp_path, l5x, capsys):
    l5x_file = tmp_path / "project.xml"
    l5x_file.write_text(KITCHEN_SINK, encoding="utf-8")
    write_snapshot(l5x.parse_string(KITCHEN_SINK), tmp_path / "snap")
    assert main([str(l5x_file), str(tmp_path / "snap")]) == 0
