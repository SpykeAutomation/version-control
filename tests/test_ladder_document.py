"""The document builder turns two parsed projects into ladder-diff cards.

It is a pure function of two parsed documents, so the tests parse small L5X
strings and assert on the cards (and the rung context) it produces.
"""
from diff.ladder import build_ladder_document
from diff.rll import align_rungs
from parsers.l5x.models import Rung

from fixtures_l5x import make_l5x


def _doc(l5x, rungs_xml, program="MainProgram", routine="MainRoutine"):
    body = (
        f'<Programs><Program Name="{program}"><Routines>'
        f'<Routine Name="{routine}" Type="RLL"><RLLContent>{rungs_xml}</RLLContent>'
        f"</Routine></Routines></Program></Programs>"
    )
    return l5x.parse_string(make_l5x(body=body))


def _rung(number, text, comment=None):
    comment_xml = f"<Comment>{comment}</Comment>" if comment else ""
    return f'<Rung Number="{number}">{comment_xml}<Text>{text}</Text></Rung>'


def test_modified_rung_becomes_one_card_with_the_element_diff(l5x):
    old = _doc(l5x, _rung(0, "XIC(A)OTE(B);"))
    new = _doc(l5x, _rung(0, "XIC(A)XIC(C)OTE(B);"))
    doc = build_ladder_document(old, new, old_label="v1", new_label="v2", commit="abc1234")

    assert doc.commit == "abc1234"
    assert len(doc.routines) == 1
    card = doc.routines[0]
    assert (card.controller, card.program, card.routine) == ("ctrllr", "MainProgram", "MainRoutine")
    assert (card.old_label, card.new_label) == ("v1", "v2")

    assert [r.status for r in card.rungs] == ["modified"]
    after_labels = [(e.label, e.status) for e in card.rungs[0].after if e.kind == "contact"]
    assert ("C", "added") in after_labels
    assert card.summary.rungs_modified == 1 and card.summary.additions == 1


def test_unchanged_routine_produces_no_card(l5x):
    same = _rung(0, "XIC(A)OTE(B);")
    doc = build_ladder_document(_doc(l5x, same), _doc(l5x, same))
    assert doc.routines == []


def test_unchanged_rungs_are_kept_as_context(l5x):
    old = _doc(l5x, _rung(0, "XIC(A)OTE(B);") + _rung(1, "XIC(C)OTE(D);"))
    new = _doc(l5x, _rung(0, "XIC(A)OTE(B);") + _rung(1, "XIC(C)XIC(E)OTE(D);"))
    card = build_ladder_document(old, new).routines[0]
    # The first rung is unchanged but still shown; the second is the edit.
    assert [r.status for r in card.rungs] == ["unchanged", "modified"]


def test_added_rung_has_an_empty_before_side(l5x):
    old = _doc(l5x, _rung(0, "XIC(A)OTE(B);"))
    new = _doc(l5x, _rung(0, "XIC(A)OTE(B);") + _rung(1, "XIC(C)OTE(D);"))
    card = build_ladder_document(old, new).routines[0]
    added = [r for r in card.rungs if r.status == "added"]
    assert len(added) == 1
    assert added[0].before == [] and added[0].new_number == 1
    assert card.summary.rungs_added == 1


def test_removed_rung_has_an_empty_after_side(l5x):
    old = _doc(l5x, _rung(0, "XIC(A)OTE(B);") + _rung(1, "XIC(C)OTE(D);"))
    new = _doc(l5x, _rung(0, "XIC(A)OTE(B);"))
    card = build_ladder_document(old, new).routines[0]
    removed = [r for r in card.rungs if r.status == "removed"]
    assert len(removed) == 1 and removed[0].after == []
    assert card.summary.rungs_removed == 1


def test_document_round_trips_through_json(l5x):
    old = _doc(l5x, _rung(0, "MOV(120,Cycle.Step);"))
    new = _doc(l5x, _rung(0, "MOV(140,Cycle.Step);"))
    doc = build_ladder_document(old, new)
    from diff.ladder_models import LadderDocument

    assert LadderDocument.model_validate_json(doc.model_dump_json()) == doc


def test_align_rungs_keeps_every_rung_with_a_status(rll):
    old = [Rung(number=0, text="XIC(A)OTE(B);"), Rung(number=1, text="XIC(C)OTE(D);")]
    new = [Rung(number=0, text="XIC(A)OTE(B);"), Rung(number=1, text="XIC(C)XIC(E)OTE(D);")]
    rows = align_rungs(old, new, lambda: rll)
    assert [r.status for r in rows] == ["unchanged", "modified"]
