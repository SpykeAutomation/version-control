"""Snapshot folder guards.

A snapshot folder must be byte-identical across exports of an unchanged
project, and a real change must touch exactly the file it belongs to.
These tests pin the folder layout, the canonical byte format, the name
guards, and the stale-file cleanup.
"""
import json
from pathlib import Path

import pytest

from parsers.l5x.models import (
    AOI,
    Controller,
    ControllerMetadata,
    DataType,
    Module,
    Program,
    Routine,
    RoutineContent,
    Tag,
    Task,
)
from snapshot import SnapshotError, snapshot_document, write_snapshot
from snapshot.__main__ import main

from fixtures_l5x import KITCHEN_SINK, make_l5x

EXPECTED_KITCHEN_SINK_PATHS = {
    "controller.json",
    "modules.json",
    "data_types.json",
    "tags.json",
    "tasks.json",
    "aois/ValveCtl.json",
    "aois/ProtValveCtl.json",
    "programs/MixerProg/program.json",
    "programs/MixerProg/tags.json",
    "programs/MixerProg/routines/Main.json",
    "programs/MixerProg/routines/Calc.json",
    "programs/MixerProg/routines/Blend.json",
    "programs/MixerProg/routines/ProtCalc.json",
}


def folder_bytes(root: Path) -> dict[str, bytes]:
    """Read a folder back as {posix relative path: raw bytes}."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_snapshots_identical_when_only_export_date_differs(tmp_path, l5x):
    redated = KITCHEN_SINK.replace(
        'ExportDate="Mon Jan 05 10:00:00 2026"',
        'ExportDate="Tue Feb 17 08:30:00 2026"',
    )
    assert redated != KITCHEN_SINK  # the marker must exist for this test to mean anything
    write_snapshot(l5x.parse_string(KITCHEN_SINK), tmp_path / "a")
    write_snapshot(l5x.parse_string(redated), tmp_path / "b")
    assert folder_bytes(tmp_path / "a") == folder_bytes(tmp_path / "b")


def test_real_change_touches_only_expected_file(l5x):
    changed = KITCHEN_SINK.replace(
        "XIC(StartPB)OTE(RunLamp);", "XIC(StartPB)XIC(EStopOk)OTE(RunLamp);"
    )
    assert changed != KITCHEN_SINK
    before = snapshot_document(l5x.parse_string(KITCHEN_SINK))
    after = snapshot_document(l5x.parse_string(changed))
    assert set(before) == set(after)
    differing = [path for path in before if before[path] != after[path]]
    assert differing == ["programs/MixerProg/routines/Main.json"]


def test_layout_and_round_trip(tmp_path, l5x):
    doc = l5x.parse_string(KITCHEN_SINK)
    write_snapshot(doc, tmp_path)
    data = {
        path: json.loads(raw.decode("utf-8"))
        for path, raw in folder_bytes(tmp_path).items()
    }
    assert set(data) == EXPECTED_KITCHEN_SINK_PATHS

    # Everything in the document survives the trip to disk and back, except
    # the dropped export date. Per-file entities (AOIs, routines) come back
    # in file-name order, so they are compared by name; their order in the
    # XML is not semantic.
    ctrl = data["controller.json"]
    assert ControllerMetadata.model_validate(ctrl["metadata"]) == doc.metadata.model_copy(
        update={"export_date": None}
    )
    assert Controller.model_validate(ctrl["controller"]) == doc.controller
    assert [Module.model_validate(m) for m in data["modules.json"]] == doc.modules
    assert [DataType.model_validate(d) for d in data["data_types.json"]] == doc.data_types
    assert [Tag.model_validate(t) for t in data["tags.json"]] == doc.controller_tags
    assert [Task.model_validate(t) for t in data["tasks.json"]] == doc.tasks

    aois = {
        path.split("/")[1].removesuffix(".json"): AOI.model_validate(data[path])
        for path in data
        if path.startswith("aois/")
    }
    assert aois == {a.name: a for a in doc.add_on_instructions}

    original = doc.programs[0]
    rebuilt = Program.model_validate(data["programs/MixerProg/program.json"])
    assert rebuilt == original.model_copy(update={"tags": [], "routines": []})
    assert [
        Tag.model_validate(t) for t in data["programs/MixerProg/tags.json"]
    ] == original.tags
    routines = {
        path.rsplit("/", 1)[1].removesuffix(".json"): Routine.model_validate(data[path])
        for path in data
        if path.startswith("programs/MixerProg/routines/")
    }
    assert routines == {r.name: r for r in original.routines}


def test_files_are_canonical_bytes(tmp_path, l5x):
    accented = KITCHEN_SINK.replace(
        "<Description>Main line controller</Description>",
        "<Description>Mélangeur — ligne 1</Description>",
    )
    assert accented != KITCHEN_SINK
    write_snapshot(l5x.parse_string(accented), tmp_path)
    contents = folder_bytes(tmp_path)
    assert contents
    for raw in contents.values():
        raw.decode("utf-8")  # must be valid UTF-8
        assert b"\r" not in raw
        assert raw.endswith(b"\n") and not raw.endswith(b"\n\n")
    # Non-ASCII text stays readable, not \uXXXX-escaped
    assert "Mélangeur — ligne 1".encode("utf-8") in contents["controller.json"]


def test_bad_name_rejected(l5x):
    doc = l5x.parse_string(make_l5x())
    doc.programs = [
        Program(
            name="GoodProg",
            routines=[Routine(name="../evil", type="RLL", content=RoutineContent())],
        )
    ]
    with pytest.raises(SnapshotError):
        snapshot_document(doc)


def test_windows_reserved_names_escaped(l5x):
    # Windows reserves device names like AUX, CON, and COM1: a file called
    # AUX.json fails or vanishes on some systems. Such names are legal in
    # Logix, so on disk they get a trailing hyphen (which no Logix name can
    # contain); the name inside the file stays unchanged.
    doc = l5x.parse_string(make_l5x())
    doc.add_on_instructions = [AOI(name="COM1")]
    doc.programs = [
        Program(
            name="Aux",
            routines=[Routine(name="CON", type="RLL", content=RoutineContent())],
        )
    ]
    files = snapshot_document(doc)
    assert "aois/COM1-.json" in files
    assert "programs/Aux-/program.json" in files
    assert "programs/Aux-/routines/CON-.json" in files
    assert json.loads(files["aois/COM1-.json"])["name"] == "COM1"
    assert json.loads(files["programs/Aux-/program.json"])["name"] == "Aux"
    assert json.loads(files["programs/Aux-/routines/CON-.json"])["name"] == "CON"


def test_case_collision_rejected(l5x):
    doc = l5x.parse_string(make_l5x())
    doc.add_on_instructions = [AOI(name="MixCtrl"), AOI(name="MIXCTRL")]
    with pytest.raises(SnapshotError):
        snapshot_document(doc)


def test_stale_files_removed_and_user_files_kept(tmp_path, l5x):
    doc = l5x.parse_string(KITCHEN_SINK)
    extra = Program(
        name="ExtraProg",
        routines=[Routine(name="Spare", type="RLL", content=RoutineContent())],
    )
    doc.programs.append(extra)
    write_snapshot(doc, tmp_path)
    (tmp_path / "notes.txt").write_text("keep me", encoding="utf-8")
    assert (tmp_path / "programs/ExtraProg/routines/Spare.json").is_file()
    assert (tmp_path / "programs/MixerProg/routines/Calc.json").is_file()

    # Drop a whole program and one routine of the remaining program
    doc.programs = [p for p in doc.programs if p.name != "ExtraProg"]
    doc.programs[0].routines = [r for r in doc.programs[0].routines if r.name != "Calc"]
    write_snapshot(doc, tmp_path)
    assert not (tmp_path / "programs/ExtraProg").exists()
    assert not (tmp_path / "programs/MixerProg/routines/Calc.json").exists()
    assert (tmp_path / "programs/MixerProg/routines/Main.json").is_file()
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "keep me"


def test_cli_writes_snapshot(tmp_path):
    l5x_file = tmp_path / "project.xml"
    l5x_file.write_text(KITCHEN_SINK, encoding="utf-8")
    out = tmp_path / "out"
    assert main([str(l5x_file), "-o", str(out)]) == 0
    assert (out / "controller.json").is_file()


def test_cli_reports_missing_file(tmp_path, capsys):
    assert main([str(tmp_path / "missing.xml"), "-o", str(tmp_path / "out")]) == 1
    assert "error:" in capsys.readouterr().err
