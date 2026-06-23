"""The element diff marks what changed inside a rung, at every nesting depth.

Each case parses an old and new rung with the real parser, diffs them, and
checks the status stamped on each element of the before and after trees.
"""
from diff.ladder import diff_rung_elements


def _flat(elements):
    """Walk a tree into (key, status) pairs; branches recurse into their legs."""
    out = []
    for el in elements:
        if el.kind == "branch":
            out.append(("branch", el.status))
            for leg in el.legs:
                out.extend(_flat(leg))
        else:
            key = el.label if el.kind in ("contact", "coil") else el.mnemonic
            out.append((key, el.status))
    return out


def _diff(rll, old_text, new_text):
    return diff_rung_elements(rll.parse(old_text), rll.parse(new_text))


def test_identical_rungs_are_all_unchanged(rll):
    before, after = _diff(rll, "XIC(A)OTE(B);", "XIC(A)OTE(B);")
    assert {s for _, s in _flat(before) + _flat(after)} == {"unchanged"}


def test_inserted_contact_is_added_only_on_the_after_side(rll):
    before, after = _diff(rll, "XIC(A)OTE(B);", "XIC(A)XIC(C)OTE(B);")
    assert _flat(before) == [("A", "unchanged"), ("B", "unchanged")]
    assert _flat(after) == [("A", "unchanged"), ("C", "added"), ("B", "unchanged")]


def test_removed_contact_is_removed_only_on_the_before_side(rll):
    before, after = _diff(rll, "XIC(A)XIC(C)OTE(B);", "XIC(A)OTE(B);")
    assert _flat(before) == [("A", "unchanged"), ("C", "removed"), ("B", "unchanged")]
    assert _flat(after) == [("A", "unchanged"), ("B", "unchanged")]


def test_box_operand_edit_is_modified_with_the_changed_row_flagged(rll):
    before, after = _diff(rll, "MOV(120,Cycle.Step);", "MOV(140,Cycle.Step);")
    assert before[0].status == "modified" and after[0].status == "modified"
    # Only the Source operand changed (120 -> 140); Dest is untouched.
    assert [o.changed for o in before[0].operands] == [True, False]
    assert [o.changed for o in after[0].operands] == [True, False]
    assert after[0].operands[0].value == "140"


def test_changed_contact_tag_reads_as_removal_plus_addition(rll):
    # A contact's tag is its identity, so a tag swap is a clean remove + add.
    before, after = _diff(rll, "XIC(Start)OTE(R);", "XIC(Stop)OTE(R);")
    assert _flat(before) == [("Start", "removed"), ("R", "unchanged")]
    assert _flat(after) == [("Stop", "added"), ("R", "unchanged")]


def test_element_added_inside_a_branch_leg(rll):
    before, after = _diff(
        rll, "XIC(A)[OTE(B),MOV(1,C)];", "XIC(A)[OTE(B)XIC(D),MOV(1,C)];"
    )
    # The added contact lands in the first leg; only that branch is modified.
    assert ("D", "added") in _flat(after)
    assert _flat(before) == [
        ("A", "unchanged"),
        ("branch", "modified"),
        ("B", "unchanged"),
        ("MOV", "unchanged"),
    ]


def test_whole_branch_leg_removed(rll):
    before, after = _diff(rll, "[XIC(A),XIC(B)]OTE(C);", "[XIC(A)]OTE(C);")
    assert ("B", "removed") in _flat(before)
    # The after branch lost a leg, so the branch itself reads as modified.
    assert _flat(after) == [
        ("branch", "modified"),
        ("A", "unchanged"),
        ("C", "unchanged"),
    ]


def test_deeply_nested_change_is_pinpointed(rll):
    # XIC(D) -> XIC(Z) two branch levels deep: only those two leaves change.
    before, after = _diff(
        rll,
        "XIC(A)[OTE(B),[XIC(C),XIC(D)]];",
        "XIC(A)[OTE(B),[XIC(C),XIC(Z)]];",
    )
    assert _flat(before) == [
        ("A", "unchanged"),
        ("branch", "modified"),
        ("B", "unchanged"),
        ("branch", "modified"),
        ("C", "unchanged"),
        ("D", "removed"),
    ]
    assert _flat(after) == [
        ("A", "unchanged"),
        ("branch", "modified"),
        ("B", "unchanged"),
        ("branch", "modified"),
        ("C", "unchanged"),
        ("Z", "added"),
    ]


def test_diff_is_deterministic(rll):
    a = _flat(_diff(rll, "XIC(A)[OTE(B),MOV(1,C)];", "XIC(A)[OTE(B)XIC(D),MOV(2,C)];")[1])
    b = _flat(_diff(rll, "XIC(A)[OTE(B),MOV(1,C)];", "XIC(A)[OTE(B)XIC(D),MOV(2,C)];")[1])
    assert a == b
