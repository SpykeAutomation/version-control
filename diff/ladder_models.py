"""
The ladder-diff IR: the data shape that describes a side-by-side ladder
diff for rendering.

This is the contract between the Python engine and any renderer (the web
app, a PDF export, a PR comment). The engine fills these models in from the
parsed rungs and the element-level diff; a renderer only draws what it is
given. No diff logic, instruction knowledge, or operand labels live in the
renderer — they are all resolved here and baked into the values below.

Two properties this shape deliberately keeps:
  * Deterministic — the IR is a pure function of its inputs. Version
    labels and commit ids are passed in by the caller; nothing is derived
    from the clock or a random source, and there are no set-ordered fields,
    so the same inputs always dump to byte-identical JSON.
  * Aligned rows — each RungDiff is one row spanning BOTH panels. The
    before panel draws `before` (+ `old_number`); the after panel draws
    `after` (+ `new_number`). A wholly added rung is a row whose `before`
    is empty and `old_number` is None; a removed rung is the mirror. That
    is how the two columns stay aligned when rungs are inserted or deleted.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# Bump when the shape below changes in a way a renderer must notice.
SCHEMA_VERSION = 1

# Per-element diff state. A "modified" element appears on both sides (e.g. a
# box whose operand value changed); which operand differs is marked on the
# operand itself, not here.
ElementStatus = Literal["unchanged", "added", "removed", "modified"]

# Per-rung diff state. "comment_changed" means the logic is identical and
# only the attached comment text differs.
RungStatus = Literal["unchanged", "added", "removed", "modified", "comment_changed"]


class Operand(BaseModel):
    """One operand row of an instruction box.

    `label` is the resolved operand name (e.g. "Source", "Preset"), empty
    when unknown or positional. `value` is the operand text as written.
    `changed` marks the single row that differs in a modified box, so the
    renderer can tint that row rather than the whole box.
    """

    label: str = ""
    value: str = ""
    changed: bool = False


class Element(BaseModel):
    """One drawable item on a rung.

    `kind` selects which of the optional fields apply:
      * "contact" → `form` ("no" | "nc"), `label` (tag text)
      * "coil"    → `form` ("ote" | "otl" | "otu"), `label`
      * "box"     → `mnemonic` (instruction or AOI name), `operands`
      * "branch"  → `legs` (parallel legs, each a list of Elements)
      * "raw"     → `text` (a rung/element the grammar could not read;
                    rendered verbatim so nothing ever crashes)
    """

    kind: Literal["contact", "coil", "box", "branch", "raw"]
    status: ElementStatus = "unchanged"

    # contact / coil
    form: Optional[str] = None
    label: Optional[str] = None

    # box
    mnemonic: Optional[str] = None
    operands: List[Operand] = []

    # branch
    legs: List[List["Element"]] = []

    # raw fallback
    text: Optional[str] = None


# `legs` refers to Element from inside Element, so resolve the forward ref
# once the class exists (mirrors parsers.rll.models.RLLBranch).
Element.model_rebuild()


class RungDiff(BaseModel):
    """One aligned row of the ladder diff (see module docstring).

    `before`/`after` are independent element sequences — elements are not
    aligned across the two panels, only rungs are. A comment-only rung
    carries its text in the comment fields with empty element lists.
    """

    status: RungStatus = "unchanged"
    old_number: Optional[int] = None
    new_number: Optional[int] = None
    old_comment: Optional[str] = None
    new_comment: Optional[str] = None
    before: List[Element] = []
    after: List[Element] = []


class RoutineSummary(BaseModel):
    """Counts for the card header. Computed by the engine, not the renderer."""

    rungs_modified: int = 0
    rungs_added: int = 0
    rungs_removed: int = 0
    additions: int = 0
    removals: int = 0


class RoutineLadderDiff(BaseModel):
    """One routine rendered as one diff card.

    `controller`/`program`/`routine` form the title breadcrumb. `old_label`
    and `new_label` are the version chips (e.g. "v14", "v15") supplied by
    the caller.
    """

    controller: Optional[str] = None
    program: Optional[str] = None
    routine: Optional[str] = None
    routine_type: str = "RLL"
    old_label: Optional[str] = None
    new_label: Optional[str] = None
    summary: RoutineSummary = Field(default_factory=RoutineSummary)
    rungs: List[RungDiff] = []


class LadderDocument(BaseModel):
    """Everything one diff produces: one card per changed ladder routine.

    `commit` is an optional caller-provided identifier for the comparison
    (e.g. a git short hash); it is never generated here, to keep the IR
    deterministic.
    """

    schema_version: int = SCHEMA_VERSION
    commit: Optional[str] = None
    routines: List[RoutineLadderDiff] = []
