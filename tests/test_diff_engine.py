"""End-to-end document diffs over the kitchen-sink fixture."""
import pytest

from diff import diff_documents

from fixtures_l5x import KITCHEN_SINK, make_l5x


def _diff_xml(l5x, rll, st, old_xml, new_xml):
    return diff_documents(
        l5x.parse_string(old_xml),
        l5x.parse_string(new_xml),
        rll_parser=rll,
        st_parser=st,
    )


def _replaced(marker, replacement):
    changed = KITCHEN_SINK.replace(marker, replacement)
    assert changed != KITCHEN_SINK, f"fixture marker not found: {marker}"
    return changed


def test_identical_documents_diff_empty(l5x, rll, st):
    assert _diff_xml(l5x, rll, st, KITCHEN_SINK, KITCHEN_SINK).is_empty()


def test_export_date_is_ignored(l5x, rll, st):
    redated = _replaced(
        'ExportDate="Mon Jan 05 10:00:00 2026"',
        'ExportDate="Tue Feb 17 08:30:00 2026"',
    )
    assert _diff_xml(l5x, rll, st, KITCHEN_SINK, redated).is_empty()


def test_export_options_are_ignored(l5x, rll, st):
    # A manual export and an SDK conversion of the same project list
    # different export options; that is not a project change.
    one = make_l5x(root_attrs='ExportOptions="NoRawData Dependencies"')
    other = make_l5x(root_attrs='ExportOptions="NoRawData"')
    assert _diff_xml(l5x, rll, st, one, other).is_empty()


def test_module_connection_change_has_named_path(l5x, rll, st):
    changed = _replaced('RPI="20000"', 'RPI="25000"')
    cs = _diff_xml(l5x, rll, st, KITCHEN_SINK, changed)
    assert [m.name for m in cs.modules] == ["EnetAdapter"]
    assert [(f.path, f.old, f.new) for f in cs.modules[0].fields] == [
        ("connections[Standard].rpi", 20000, 25000)
    ]


def test_tag_value_change_reports_member_path(l5x, rll, st):
    changed = _replaced('<DataValueMember Name="Mode" Value="2"/>',
                        '<DataValueMember Name="Mode" Value="7"/>')
    cs = _diff_xml(l5x, rll, st, KITCHEN_SINK, changed)
    assert [t.name for t in cs.controller_tags] == ["MixerState"]
    assert [(f.path, f.old, f.new) for f in cs.controller_tags[0].fields] == [
        ("values.Mode", "2", "7")
    ]


def test_protected_aoi_signature_change_detected(l5x, rll, st):
    changed = _replaced('SignatureID="16#1234_abcd"', 'SignatureID="16#9999_ffff"')
    cs = _diff_xml(l5x, rll, st, KITCHEN_SINK, changed)
    assert [a.name for a in cs.add_on_instructions] == ["ProtValveCtl"]
    assert [f.path for f in cs.add_on_instructions[0].fields] == ["signature_id"]


def test_rung_edit_reports_one_modified_rung(l5x, rll, st):
    changed = _replaced("XIC(StartPB)OTE(RunLamp);", "XIC(StartPB)XIC(GateOk)OTE(RunLamp);")
    cs = _diff_xml(l5x, rll, st, KITCHEN_SINK, changed)
    assert [p.name for p in cs.programs] == ["MixerProg"]
    routines = cs.programs[0].routines
    assert [(r.name, len(r.rungs)) for r in routines] == [("Main", 1)]
    assert routines[0].rungs[0].kind == "modified"


def test_st_line_edit_reported(l5x, rll, st):
    changed = _replaced("StepNo := 1;", "StepNo := 2;")
    cs = _diff_xml(l5x, rll, st, KITCHEN_SINK, changed)
    routines = cs.programs[0].routines
    assert [(r.name, len(r.lines)) for r in routines] == [("Calc", 1)]
    assert routines[0].lines[0].kind == "modified"


def test_fbd_change_gets_not_parsed_note(l5x, rll, st):
    changed = _replaced('SheetSize="Letter"', 'SheetSize="A4"')
    cs = _diff_xml(l5x, rll, st, KITCHEN_SINK, changed)
    routines = cs.programs[0].routines
    assert [(r.name, r.note) for r in routines] == [("Blend", "changed (not yet parsed)")]


def test_routine_type_change_noted(l5x, rll, st):
    changed = _replaced(
        '<Routine Name="Calc" Type="ST">'
        '<STContent><Line Number="0"><Text>StepNo := 1;</Text></Line></STContent>'
        "</Routine>",
        '<Routine Name="Calc" Type="RLL">'
        '<RLLContent><Rung Number="0"><Text>NOP();</Text></Rung></RLLContent>'
        "</Routine>",
    )
    cs = _diff_xml(l5x, rll, st, KITCHEN_SINK, changed)
    routine = cs.programs[0].routines[0]
    assert routine.note == "content replaced (routine type changed)"
    assert ("type", "ST", "RLL") in [(f.path, f.old, f.new) for f in routine.fields]


def test_program_added_and_removed(l5x, rll, st):
    one = make_l5x(body='<Programs><Program Name="OnlyInOld"/></Programs>')
    other = make_l5x(body='<Programs><Program Name="OnlyInNew"/></Programs>')
    cs = _diff_xml(l5x, rll, st, one, other)
    assert [(p.name, p.kind) for p in cs.programs] == [
        ("OnlyInNew", "added"),
        ("OnlyInOld", "removed"),
    ]


def test_diff_json_is_deterministic(l5x, rll, st):
    changed = _replaced("XIC(StartPB)OTE(RunLamp);", "XIC(StartPB)XIC(GateOk)OTE(RunLamp);")
    first = _diff_xml(l5x, rll, st, KITCHEN_SINK, changed).model_dump_json(indent=2)
    second = _diff_xml(l5x, rll, st, KITCHEN_SINK, changed).model_dump_json(indent=2)
    assert first == second


def test_snapshot_round_trip_diffs_empty(tmp_path, l5x, rll, st):
    from snapshot import read_snapshot, write_snapshot

    doc = l5x.parse_string(KITCHEN_SINK)
    write_snapshot(doc, tmp_path)
    back = read_snapshot(tmp_path)
    assert diff_documents(doc, back, rll_parser=rll, st_parser=st).is_empty()


def test_duplicate_names_rejected(l5x, rll, st):
    # Names are unique in a valid project; a duplicate would otherwise
    # silently shadow one entity and hide its changes from the diff.
    dup = make_l5x(
        body='<Tags><Tag Name="SameTag" DataType="DINT"/>'
        '<Tag Name="SameTag" DataType="DINT"/></Tags>'
    )
    with pytest.raises(ValueError, match="SameTag"):
        _diff_xml(l5x, rll, st, dup, dup)
