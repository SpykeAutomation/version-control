"""Rung matching: renumbering is invisible, edits pair up, comments stay separate."""
from diff.rll import diff_rungs
from parsers.l5x.models import Rung


def R(number, text=None, comment=None, type="N"):
    return Rung(number=number, type=type, comment=comment, text=text)


def _diff(old, new, rll):
    return diff_rungs(old, new, lambda: rll)


BASE = [
    R(0, "XIC(AutoMode)OTE(FillEnable);"),
    R(1, "XIC(FillEnable)TON(FillTimer,5000,0);"),
    R(2, "XIC(FillTimer.DN)OTE(ValveClose);"),
    R(3, "XIC(ValveClose)OTE(CycleDone);"),
]


def _renumber(rungs):
    return [r.model_copy(update={"number": i}) for i, r in enumerate(rungs)]


def test_identical_is_empty(rll):
    assert _diff(BASE, [r.model_copy() for r in BASE], rll) == []


def test_append_is_one_added(rll):
    new = _renumber(BASE + [R(0, "XIC(CycleDone)OTE(Lamp);")])
    changes = _diff(BASE, new, rll)
    assert [(c.kind, c.new_number) for c in changes] == [("added", 4)]


def test_insert_in_middle_is_exactly_one_added(rll):
    # Everything after the insert gets renumbered — the classic false-diff trap
    new = _renumber(BASE[:1] + [R(0, "XIC(LevelOK)OTE(FillPermit);")] + BASE[1:])
    changes = _diff(BASE, new, rll)
    assert [(c.kind, c.new_number, c.new_text) for c in changes] == [
        ("added", 1, "XIC(LevelOK)OTE(FillPermit);")
    ]


def test_delete_is_one_removed(rll):
    new = _renumber(BASE[:1] + BASE[2:])
    changes = _diff(BASE, new, rll)
    assert [(c.kind, c.old_number) for c in changes] == [("removed", 1)]


def test_edit_is_one_modified(rll):
    new = [r.model_copy() for r in BASE]
    new[1] = R(1, "XIC(FillEnable)TON(FillTimer,7500,0);")
    changes = _diff(BASE, new, rll)
    assert [(c.kind, c.old_number, c.new_number) for c in changes] == [("modified", 1, 1)]
    assert "5000" in changes[0].old_text and "7500" in changes[0].new_text


def test_moved_rung_reports_removed_and_added(rll):
    # Order changes execution, so a move is reported honestly as both sides
    new = _renumber(BASE[1:] + BASE[:1])
    kinds = sorted(c.kind for c in _diff(BASE, new, rll))
    assert kinds == ["added", "removed"]


def test_comment_only_edit_is_comment_changed(rll):
    old = [R(0, "XIC(A)OTE(B);", comment="start gate")]
    new = [R(0, "XIC(A)OTE(B);", comment="start gate, rev B")]
    changes = _diff(old, new, rll)
    assert [(c.kind, c.old_comment, c.new_comment) for c in changes] == [
        ("comment_changed", "start gate", "start gate, rev B")
    ]


def test_comment_rung_edit_is_modified(rll):
    old = [R(0, type="C", comment="section: filling")]
    new = [R(0, type="C", comment="section: filling and dosing")]
    changes = _diff(old, new, rll)
    assert [(c.kind, c.old_comment, c.new_comment) for c in changes] == [
        ("modified", "section: filling", "section: filling and dosing")
    ]


def test_whitespace_only_edit_is_dropped(rll):
    old = [R(0, "XIC(A)OTE(B);")]
    new = [R(0, "XIC(A)  OTE( B );")]
    assert _diff(old, new, rll) == []


def test_replace_block_mixes_modified_and_added(rll):
    old = [R(0, "XIC(A)OTE(B);"), R(1, "XIC(C)OTE(D);")]
    new = [
        R(0, "XIC(A)XIC(Ok)OTE(B);"),  # edit of old rung 0
        R(1, "MOV(1,StepNo);"),        # genuinely new
        R(2, "XIC(C)OTE(D);"),         # unchanged, renumbered
    ]
    changes = _diff(old, new, rll)
    assert sorted((c.kind, c.new_number) for c in changes) == [
        ("added", 1),
        ("modified", 0),
    ]


def test_many_repeated_rungs_still_match(rll):
    # autojunk regression guard: repeated identical rungs must not be
    # discarded as noise by the sequence matcher
    old = [R(i, "NOP();") for i in range(300)]
    new = _renumber(old[:150] + [R(0, "XIC(NewBit)OTE(NewOut);")] + old[150:])
    changes = _diff(old, new, rll)
    assert [(c.kind, c.new_number) for c in changes] == [("added", 150)]
