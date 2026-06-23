"""Reader guards: a snapshot folder must load back into the same document."""
import pytest

from parsers.l5x.models import AOI
from snapshot import SnapshotError, read_snapshot, write_snapshot

from fixtures_l5x import KITCHEN_SINK, make_l5x


def _by_name(items):
    return {item.name: item for item in items}


def test_round_trip(tmp_path, l5x):
    doc = l5x.parse_string(KITCHEN_SINK)
    write_snapshot(doc, tmp_path)
    back = read_snapshot(tmp_path)

    # Everything survives except the dropped export date. Per-file entities
    # come back in file-name order, so they are compared by name.
    assert back.metadata == doc.metadata.model_copy(update={"export_date": None})
    assert back.controller == doc.controller
    assert back.modules == doc.modules
    assert back.data_types == doc.data_types
    assert back.controller_tags == doc.controller_tags
    assert back.tasks == doc.tasks
    assert _by_name(back.add_on_instructions) == _by_name(doc.add_on_instructions)
    assert {p.name for p in back.programs} == {p.name for p in doc.programs}
    for program in back.programs:
        original = next(p for p in doc.programs if p.name == program.name)
        assert program.tags == original.tags
        assert _by_name(program.routines) == _by_name(original.routines)
        assert program.model_dump(exclude={"tags", "routines"}) == original.model_dump(
            exclude={"tags", "routines"}
        )


def test_reserved_name_round_trip(tmp_path, l5x):
    doc = l5x.parse_string(make_l5x())
    doc.add_on_instructions = [AOI(name="Aux")]
    write_snapshot(doc, tmp_path)
    back = read_snapshot(tmp_path)
    assert [a.name for a in back.add_on_instructions] == ["Aux"]


def test_missing_folder_rejected(tmp_path):
    with pytest.raises(SnapshotError):
        read_snapshot(tmp_path / "nothing_here")


def test_missing_file_rejected(tmp_path, l5x):
    write_snapshot(l5x.parse_string(make_l5x()), tmp_path)
    (tmp_path / "controller.json").unlink()
    with pytest.raises(SnapshotError, match="controller.json"):
        read_snapshot(tmp_path)


def test_corrupt_file_names_the_file(tmp_path, l5x):
    write_snapshot(l5x.parse_string(make_l5x()), tmp_path)
    (tmp_path / "tags.json").write_text("not json", encoding="utf-8")
    with pytest.raises(SnapshotError, match="tags.json"):
        read_snapshot(tmp_path)


def test_wrong_controller_shape_names_the_file(tmp_path, l5x):
    write_snapshot(l5x.parse_string(make_l5x()), tmp_path)
    (tmp_path / "controller.json").write_text("[]", encoding="utf-8")
    with pytest.raises(SnapshotError, match="controller.json"):
        read_snapshot(tmp_path)


def test_wrong_program_shape_names_the_file(tmp_path, l5x):
    doc = l5x.parse_string(make_l5x(body='<Programs><Program Name="Prog"/></Programs>'))
    write_snapshot(doc, tmp_path)
    (tmp_path / "programs" / "Prog" / "program.json").write_text("[]", encoding="utf-8")
    with pytest.raises(SnapshotError, match="program.json"):
        read_snapshot(tmp_path)
