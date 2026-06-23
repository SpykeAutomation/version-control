"""Semantic diff: compare two versions of a PLC project in PLC terms."""
from .engine import diff_documents, diff_named
from .ladder import build_ladder_document
from .ladder_models import (
    Element,
    LadderDocument,
    Operand,
    RoutineLadderDiff,
    RoutineSummary,
    RungDiff,
)
from .models import (
    ChangeSet,
    EntityChange,
    FieldChange,
    LineChange,
    ProgramChange,
    RoutineChange,
    RungChange,
)
from .render import render_text

__all__ = [
    "ChangeSet",
    "EntityChange",
    "FieldChange",
    "LineChange",
    "ProgramChange",
    "RoutineChange",
    "RungChange",
    # ladder-diagram (visual) diff
    "Element",
    "LadderDocument",
    "Operand",
    "RoutineLadderDiff",
    "RoutineSummary",
    "RungDiff",
    "build_ladder_document",
    # entry points
    "diff_documents",
    "diff_named",
    "render_text",
]
