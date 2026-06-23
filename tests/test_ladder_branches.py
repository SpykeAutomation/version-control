"""Parallel branches classify into nested leg structures.

classify() recurses into branches; these pin the real-world branch shapes —
the parallel-output shape and the awkward cases (empty bypass legs, series
legs, nesting).
"""
from diff.ladder import classify, classify_rung


def test_output_branch_holds_a_coil_and_a_box(rll):
    # One rung driving a coil and a MOV in parallel.
    els = classify_rung(rll.parse("XIC(A)[OTE(B),MOV(120,Cycle.Step)];"))
    assert [e.kind for e in els] == ["contact", "branch"]

    branch = els[1]
    assert len(branch.legs) == 2
    top, bottom = branch.legs
    assert (top[0].kind, top[0].form, top[0].label) == ("coil", "ote", "B")
    assert bottom[0].kind == "box" and bottom[0].mnemonic == "MOV"
    assert [(o.label, o.value) for o in bottom[0].operands] == [
        ("Source", "120"),
        ("Dest", "Cycle.Step"),
    ]


def test_empty_bypass_leg_becomes_an_empty_list(rll):
    # A branch with a straight-wire bypass path is valid ladder, not an error.
    branch = classify(rll.parse("[XIC(A),]OTE(B);").elements[0])
    assert branch.kind == "branch"
    assert [len(leg) for leg in branch.legs] == [1, 0]
    assert branch.legs[1] == []


def test_a_leg_keeps_its_instructions_in_series(rll):
    # leg 0 has two instructions in series; leg 1 has one.
    branch = classify(rll.parse("[XIC(A)OTE(B),XIC(C)];").elements[0])
    assert [[e.kind for e in leg] for leg in branch.legs] == [
        ["contact", "coil"],
        ["contact"],
    ]


def test_nested_branch_produces_a_branch_inside_a_leg(rll):
    branch = classify(rll.parse("[XIC(A),[XIC(B),XIC(C)]]OTE(D);").elements[0])
    inner = branch.legs[1][0]
    assert inner.kind == "branch"
    assert [leg[0].label for leg in inner.legs] == ["B", "C"]


def test_output_branch_with_a_bypass_leg(rll):
    branch = classify(rll.parse("XIC(En)[OTL(M),];").elements[1])
    assert branch.kind == "branch"
    assert (branch.legs[0][0].kind, branch.legs[0][0].form) == ("coil", "otl")
    assert branch.legs[1] == []
