"""classify() maps one parsed instruction to one drawable element.

Rungs are parsed with the real RLL parser so the operand tokens (and their
text reconstruction) match what the engine actually sees.
"""
import pytest

from diff.ladder import LabelResolver, classify, classify_rung
from parsers.rll.models import RLLBranch, RLLInstruction


def _one(rll, text):
    """Parse a single-element rung and return that element's classification."""
    parsed = rll.parse(text)
    assert len(parsed.elements) == 1
    return classify(parsed.elements[0])


def test_xic_is_a_normally_open_contact(rll):
    el = _one(rll, "XIC(Start);")
    assert (el.kind, el.form, el.label) == ("contact", "no", "Start")
    assert el.status == "unchanged"  # no diff applied yet


def test_xio_is_a_normally_closed_contact(rll):
    el = _one(rll, "XIO(Stop);")
    assert (el.kind, el.form, el.label) == ("contact", "nc", "Stop")


@pytest.mark.parametrize("name,form", [("OTE", "ote"), ("OTL", "otl"), ("OTU", "otu")])
def test_output_coils(rll, name, form):
    el = _one(rll, f"{name}(Motor);")
    assert (el.kind, el.form, el.label) == ("coil", form, "Motor")


def test_box_pairs_values_with_operand_labels(rll):
    el = _one(rll, "MOV(120,Cycle.Step);")
    assert el.kind == "box" and el.mnemonic == "MOV"
    assert [(o.label, o.value) for o in el.operands] == [
        ("Source", "120"),
        ("Dest", "Cycle.Step"),
    ]


def test_unknown_instruction_falls_back_to_positional_box(rll):
    el = _one(rll, "ZZTOP(a,b);")
    assert el.kind == "box" and el.mnemonic == "ZZTOP"
    # No labels known -> bare values, never crashes.
    assert [(o.label, o.value) for o in el.operands] == [("", "a"), ("", "b")]


def test_extra_operands_beyond_known_labels_stay_unlabeled(rll):
    # JSR knows only "Routine Name"; the variadic in/return params are bare.
    el = _one(rll, "JSR(MyRoutine,In1,Out1);")
    assert [(o.label, o.value) for o in el.operands] == [
        ("Routine Name", "MyRoutine"),
        ("", "In1"),
        ("", "Out1"),
    ]


def test_empty_operand_keeps_an_empty_value(rll):
    # GSV(Class,,Attr,Dest) — the blank slot is a real, empty operand.
    el = _one(rll, "GSV(Module,,Attr,Dest);")
    assert el.operands[1].value == ""


def test_branch_recurses_into_each_leg(rll):
    parsed = rll.parse("[XIC(A),XIO(B)]OTE(C);")
    branch = classify(parsed.elements[0])
    assert branch.kind == "branch" and len(branch.legs) == 2
    assert branch.legs[0][0].label == "A" and branch.legs[0][0].form == "no"
    assert branch.legs[1][0].label == "B" and branch.legs[1][0].form == "nc"


def test_classify_rung_returns_every_top_level_element(rll):
    els = classify_rung(rll.parse("XIC(Start)MOV(120,Cycle.Step)OTE(Run);"))
    assert [e.kind for e in els] == ["contact", "box", "coil"]


def test_aoi_operands_resolve_from_the_resolver_overlay():
    # A user AOI is unknown to the built-in table; its labels come from the
    # project's parsed parameter names.
    resolver = LabelResolver(aoi_operands={"ValveCtl": ["Valve", "Command", "Status"]})
    instr = RLLInstruction(name="ValveCtl", params=[])
    parsed_instr = _make(instr, ["V1", "Open", "Sts"])
    el = classify(parsed_instr, resolver)
    assert el.kind == "box"
    assert [(o.label, o.value) for o in el.operands] == [
        ("Valve", "V1"),
        ("Command", "Open"),
        ("Status", "Sts"),
    ]


def _make(instr, values):
    from parsers.rll.models import RLLParam

    instr.params = [RLLParam(tokens=[v]) for v in values]
    return instr
