"""The ladder-diff IR is a contract, so pin its shape and its guarantees.

These tests do not exercise any logic (there is none yet in P1) — they pin
that the models build, survive a JSON round-trip, and dump deterministically,
since a renderer on the other side builds against exactly this output.
"""
import json

from diff.ladder_models import (
    SCHEMA_VERSION,
    Element,
    LadderDocument,
    Operand,
    RoutineLadderDiff,
    RoutineSummary,
    RungDiff,
)


def _sample_document() -> LadderDocument:
    """A small but representative document touching every element kind."""
    equ = Element(
        kind="box",
        mnemonic="EQU",
        operands=[
            Operand(label="Source A", value="Cycle.Step"),
            Operand(label="Source B", value="100"),
        ],
    )
    added_contact = Element(kind="contact", status="added", form="no", label="Auto")
    removed_coil = Element(kind="coil", status="removed", form="ote", label="Run")
    branch = Element(
        kind="branch",
        legs=[
            [Element(kind="coil", form="otl", label="Latch")],
            [Element(kind="raw", text="MOV(140,Cycle.Step)")],
        ],
    )

    modified_rung = RungDiff(
        status="modified",
        old_number=1,
        new_number=1,
        before=[equ],
        after=[equ, added_contact, branch],
    )
    # A wholly added rung: an aligned row with no before side.
    added_rung = RungDiff(status="added", new_number=2, after=[removed_coil])

    return LadderDocument(
        commit="abc1234",
        routines=[
            RoutineLadderDiff(
                controller="MyController",
                program="MainProgram",
                routine="MainRoutine",
                old_label="v14",
                new_label="v15",
                summary=RoutineSummary(rungs_modified=1, rungs_added=1, additions=3, removals=1),
                rungs=[modified_rung, added_rung],
            )
        ],
    )


def test_round_trips_through_json():
    doc = _sample_document()
    restored = LadderDocument.model_validate_json(doc.model_dump_json())
    assert restored == doc


def test_dump_is_deterministic():
    # Two independently built but equal documents must dump byte-identically;
    # the engine relies on same-inputs -> same-bytes for its diff guarantee.
    assert _sample_document().model_dump_json() == _sample_document().model_dump_json()


def test_document_carries_schema_version():
    payload = json.loads(_sample_document().model_dump_json())
    assert payload["schema_version"] == SCHEMA_VERSION


def test_defaults_are_quiet():
    # Anything not explicitly diffed defaults to unchanged / not-changed.
    assert Element(kind="contact").status == "unchanged"
    assert Operand().changed is False
    assert RungDiff().status == "unchanged"
    assert RungDiff().before == [] and RungDiff().after == []


def test_summary_default_is_not_shared():
    # A mutable default leaking across instances would silently merge counts.
    a = RoutineLadderDiff()
    a.summary.additions = 5
    assert RoutineLadderDiff().summary.additions == 0
