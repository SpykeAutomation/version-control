"""Turn parsed ladder logic into drawable elements, and diff two of them.

The parser says *what is written* (an instruction name and its operand
tokens); the instruction reference says *what it means* (a glyph and operand
labels). ``classify`` joins the two into one ``Element`` the renderer can draw.

``diff_rung_elements`` then compares the element trees of two versions of a
rung and marks every element added, removed, modified, or unchanged — the
before/after pair a side-by-side view needs.
"""
from __future__ import annotations

import difflib
from functools import lru_cache
from typing import Iterable, Optional

from parsers.l5x.models import AOI, L5XDocument, Routine
from parsers.rll import RLLParser
from parsers.rll.instructions import instruction_table
from parsers.rll.models import ParsedRung, RLLBranch, RLLInstruction, RLLNode

from .ladder_models import (
    Element,
    LadderDocument,
    Operand,
    RoutineLadderDiff,
    RoutineSummary,
    RungDiff,
)
from .rll import RungRow, align_rungs

# An AOI's automatic enable parameters are never passed in a call.
_ENABLE_PARAMS = frozenset({"EnableIn", "EnableOut"})


class LabelResolver:
    """Resolves an instruction mnemonic to its glyph and operand labels.

    Built from the static built-in table; ``aoi_operands`` overlays
    per-project AOI definitions (an AOI call maps positionally onto its
    parameter names). Built-ins win over AOIs on a name clash, since a
    project cannot redefine a built-in instruction.
    """

    def __init__(
        self,
        *,
        aoi_operands: Optional[dict[str, list[str]]] = None,
    ) -> None:
        self._builtins = instruction_table()
        self._aoi = aoi_operands or {}

    def lookup(self, name: str) -> Optional[dict]:
        """The display spec for ``name``, or None if it is unknown.

        A known built-in returns its table entry; a known AOI returns a box
        spec built from its parameter names; anything else returns None so the
        caller can fall back to a generic box.
        """
        spec = self._builtins.get(name)
        if spec is not None:
            return spec
        labels = self._aoi.get(name)
        if labels is not None:
            # An AOI executes on power flow, so it reads as an output.
            return {"display": "box", "form": None, "role": "output", "operands": labels}
        return None

    def role(self, name: str) -> str:
        """Whether instruction ``name`` reads ("input") or writes ("output").

        Unknown box-shaped instructions default to "output" — most are actions —
        so only the known compare/test instructions stay on the input side.
        """
        spec = self._builtins.get(name)
        if spec is not None:
            return spec.get("role", "output")
        return "output"


def aoi_operand_labels(aois: Iterable[AOI]) -> dict[str, list[str]]:
    """Operand-row labels for each AOI, keyed by AOI name.

    A user AOI is not in the built-in table; its operand names live in the
    project's own definition. An instance call reads
    ``AOIName(backing_tag, arg1, arg2, ...)``: the backing tag comes first
    (unlabeled — it is the instance, not a parameter), then one argument per
    required parameter in definition order. The automatic EnableIn/EnableOut
    parameters are never passed, so they are skipped.

    Feed the result to ``LabelResolver(aoi_operands=...)`` so ``classify`` can
    label AOI boxes the same way it labels built-ins.
    """
    table: dict[str, list[str]] = {}
    for aoi in aois:
        labels = [""]  # the backing-tag row
        labels.extend(
            p.name
            for p in aoi.parameters
            if p.required and p.name not in _ENABLE_PARAMS
        )
        table[aoi.name] = labels
    return table


def classify(node: RLLNode, resolver: Optional[LabelResolver] = None) -> Element:
    """Build the drawable ``Element`` for one parsed rung node.

    A branch becomes a branch element whose legs are classified in turn; an
    instruction becomes a contact, coil, or box. An unknown mnemonic still
    draws — as a box with positional, unlabeled operands — so a rung never
    fails to render.
    """
    resolver = resolver or LabelResolver()

    if isinstance(node, RLLBranch):
        return Element(
            kind="branch",
            legs=[[classify(n, resolver) for n in leg] for leg in node.legs],
        )

    # RLLInstruction
    values = [p.text for p in node.params]
    spec = resolver.lookup(node.name)
    display = spec["display"] if spec else "box"

    if display == "contact":
        return Element(kind="contact", form=spec.get("form"), label=values[0] if values else "")
    if display == "coil":
        return Element(kind="coil", form=spec.get("form"), label=values[0] if values else "")

    labels = spec["operands"] if spec else []
    return _box(node.name, values, labels)


def classify_rung(parsed: ParsedRung, resolver: Optional[LabelResolver] = None) -> list[Element]:
    """Classify every top-level node of a parsed rung."""
    resolver = resolver or LabelResolver()
    return [classify(n, resolver) for n in parsed.elements]


def _element_role(el: Element, resolver: LabelResolver) -> str:
    """Whether an element belongs on a rung's input (read) or output (write) side.

    Contacts read and coils write by definition; a box defers to the instruction
    reference; a branch is an output if any element inside any of its legs is —
    so a parallel output (e.g. branched coils) stays on the right, while a
    branch of conditions stays on the left. A raw fallback is left in place.
    """
    if el.kind == "coil":
        return "output"
    if el.kind == "contact":
        return "input"
    if el.kind == "box":
        return resolver.role(el.mnemonic or "")
    if el.kind == "branch":
        nested = (e for leg in el.legs for e in leg)
        return "output" if any(_element_role(e, resolver) == "output" for e in nested) else "input"
    return "input"


def order_io(elements: list[Element], resolver: LabelResolver) -> list[Element]:
    """Lay a rung out the way ladder logic reads: inputs left, outputs right.

    A stable partition — reads keep their order, writes keep theirs, and every
    read comes before every write. A valid rung is already in this order, so
    this only tidies cases where the source order differs. Branch legs are
    ordered the same way in turn.
    """
    for el in elements:
        if el.kind == "branch":
            el.legs = [order_io(leg, resolver) for leg in el.legs]
    reads, writes = [], []
    for el in elements:
        role = _element_role(el, resolver)
        el.io = role
        (writes if role == "output" else reads).append(el)
    return reads + writes


def _box(mnemonic: str, values: list[str], labels: list[str]) -> Element:
    """A box element pairing each operand value with its label.

    Values without a matching label (e.g. the variadic operands of JSR, or any
    unknown instruction) keep an empty label and render as bare values.
    """
    operands = [
        Operand(label=labels[i] if i < len(labels) else "", value=val)
        for i, val in enumerate(values)
    ]
    return Element(kind="box", mnemonic=mnemonic, operands=operands)


# ---------------------------------------------------------------------------
# Element-level diff
# ---------------------------------------------------------------------------


def diff_rung_elements(
    old: ParsedRung,
    new: ParsedRung,
    resolver_old: Optional[LabelResolver] = None,
    resolver_new: Optional[LabelResolver] = None,
) -> tuple[list[Element], list[Element]]:
    """Compare two parsed rungs into before/after element trees.

    Both rungs are classified, then every element is stamped with its status.
    The before tree (the old panel) carries the removed and modified-old
    marks; the after tree (the new panel) carries added and modified-new.
    Neither side drops or reorders its own elements — each panel shows its
    whole rung — so the two returned trees are just the classified rungs with
    statuses written in.

    Branches are compared recursively, so a change at any nesting depth is
    pinned to the exact element that differs rather than the branch around it.
    """
    before = classify_rung(old, resolver_old)
    after = classify_rung(new, resolver_new)
    _stamp_sequence(before, after)
    return before, after


def _stamp_sequence(old_els: list[Element], new_els: list[Element]) -> None:
    """Align two sibling element lists and stamp each element's status.

    A first pass lines up identical runs (left as unchanged); whatever does
    not line up is handed to ``_stamp_block`` to pair or mark added/removed.
    """
    matcher = difflib.SequenceMatcher(
        None, [_exact_key(e) for e in old_els], [_exact_key(e) for e in new_els], autojunk=False
    )
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue  # identical subtrees keep the default "unchanged"
        if op == "delete":
            _stamp_tree(old_els[i1:i2], "removed")
        elif op == "insert":
            _stamp_tree(new_els[j1:j2], "added")
        else:  # replace
            _stamp_block(old_els[i1:i2], new_els[j1:j2])


def _stamp_block(old_block: list[Element], new_block: list[Element]) -> None:
    """Pair elements within one disagreeing run.

    A coarser key matches a box to a box of the same instruction (an operand
    edit) and a branch to a branch (recurse); contacts and coils only match
    when identical, so a changed one reads as a clean removal plus addition.
    """
    matcher = difflib.SequenceMatcher(
        None, [_coarse_key(e) for e in old_block], [_coarse_key(e) for e in new_block], autojunk=False
    )
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            for o, n in zip(old_block[i1:i2], new_block[j1:j2]):
                _stamp_pair(o, n)
        elif op == "delete":
            _stamp_tree(old_block[i1:i2], "removed")
        elif op == "insert":
            _stamp_tree(new_block[j1:j2], "added")
        else:  # replace — different kinds/instructions, so not the same element
            _stamp_tree(old_block[i1:i2], "removed")
            _stamp_tree(new_block[j1:j2], "added")


def _stamp_pair(old: Element, new: Element) -> None:
    """Stamp one matched old/new element that may still differ inside."""
    if _exact_key(old) == _exact_key(new):
        return  # identical — leave as unchanged
    if old.kind == "branch" and new.kind == "branch":
        _stamp_branch(old, new)
    elif old.kind == "box" and new.kind == "box":
        _mark_box(old, new)
    else:  # same coarse key but not identical (e.g. a raw fallback edit)
        old.status = "modified"
        new.status = "modified"


def _stamp_branch(old: Element, new: Element) -> None:
    """Recurse into a changed branch, aligning legs before its elements.

    A leg with no counterpart is wholly added or removed; paired legs are
    diffed in turn. The branch itself is marked modified because its content
    differs (it only reaches here when the two branches are not identical).
    """
    matcher = difflib.SequenceMatcher(
        None, [_leg_key(l) for l in old.legs], [_leg_key(l) for l in new.legs], autojunk=False
    )
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        if op == "delete":
            for leg in old.legs[i1:i2]:
                _stamp_tree(leg, "removed")
        elif op == "insert":
            for leg in new.legs[j1:j2]:
                _stamp_tree(leg, "added")
        else:  # replace — pair legs by position, recurse; extras added/removed
            paired = min(i2 - i1, j2 - j1)
            for k in range(paired):
                _stamp_sequence(old.legs[i1 + k], new.legs[j1 + k])
            for leg in old.legs[i1 + paired:i2]:
                _stamp_tree(leg, "removed")
            for leg in new.legs[j1 + paired:j2]:
                _stamp_tree(leg, "added")
    old.status = "modified"
    new.status = "modified"


def _mark_box(old: Element, new: Element) -> None:
    """Mark two same-instruction boxes modified and flag the operands that differ."""
    old.status = "modified"
    new.status = "modified"
    old_values = [o.value for o in old.operands]
    new_values = [o.value for o in new.operands]
    for i, operand in enumerate(old.operands):
        operand.changed = i >= len(new_values) or operand.value != new_values[i]
    for i, operand in enumerate(new.operands):
        operand.changed = i >= len(old_values) or operand.value != old_values[i]


def _stamp_tree(elements: list[Element], status: str) -> None:
    """Mark every element in a wholly added or removed subtree."""
    for el in elements:
        el.status = status
        for leg in el.legs:
            _stamp_tree(leg, status)


def _exact_key(el: Element) -> tuple:
    """Content identity of an element, ignoring display-only fields.

    Two elements share this key only when they are the same drawing of the
    same logic. Operand *labels* are left out — they come from the instruction
    reference, not the rung — so a relabelled-but-unchanged operand is not a
    change.
    """
    if el.kind in ("contact", "coil"):
        return (el.kind, el.form, el.label)
    if el.kind == "box":
        return ("box", el.mnemonic, tuple(o.value for o in el.operands))
    if el.kind == "branch":
        return ("branch", tuple(tuple(_exact_key(e) for e in leg) for leg in el.legs))
    return ("raw", el.text)


def _coarse_key(el: Element) -> tuple:
    """Identity for pairing: a box by instruction, a branch as a branch.

    Boxes match by mnemonic so an operand edit pairs as one modified box;
    branches all share a key so they pair and recurse. Contacts and coils
    fall back to their exact key, so a changed one is a removal plus addition
    rather than an in-place edit.
    """
    if el.kind == "box":
        return ("box", el.mnemonic)
    if el.kind == "branch":
        return ("branch",)
    return _exact_key(el)


def _leg_key(leg: list[Element]) -> tuple:
    """Content identity of a branch leg, for aligning legs against each other."""
    return tuple(_exact_key(e) for e in leg)


# ---------------------------------------------------------------------------
# Document builder
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _default_parser() -> RLLParser:
    return RLLParser()


def build_ladder_document(
    old: L5XDocument,
    new: L5XDocument,
    *,
    old_label: Optional[str] = None,
    new_label: Optional[str] = None,
    commit: Optional[str] = None,
    rll_parser: Optional[RLLParser] = None,
) -> LadderDocument:
    """Build the ladder-diff document for two versions of a project.

    A pure function of its inputs: it takes two already-parsed documents (and
    the version labels to show) and returns the render-ready IR. It reads no
    files and knows nothing about git — a caller resolves the two versions and
    supplies the labels.

    One card is produced per ladder routine that has a real rung change; each
    card shows the whole routine, unchanged rungs kept in place for context.
    """
    parser = rll_parser or _default_parser()
    resolver_old = LabelResolver(aoi_operands=aoi_operand_labels(old.add_on_instructions))
    resolver_new = LabelResolver(aoi_operands=aoi_operand_labels(new.add_on_instructions))
    controller = getattr(new.controller, "name", None) or getattr(old.controller, "name", None)

    old_programs = {p.name: p for p in old.programs}
    new_programs = {p.name: p for p in new.programs}

    routines: list[RoutineLadderDiff] = []
    for prog_name in sorted(old_programs.keys() & new_programs.keys()):
        old_routines = {r.name: r for r in old_programs[prog_name].routines}
        new_routines = {r.name: r for r in new_programs[prog_name].routines}
        for rt_name in sorted(old_routines.keys() & new_routines.keys()):
            o_rt, n_rt = old_routines[rt_name], new_routines[rt_name]
            if o_rt == n_rt or o_rt.type != "RLL" or n_rt.type != "RLL":
                continue
            card = _build_routine(
                controller, prog_name, rt_name, o_rt, n_rt,
                old_label, new_label, parser, resolver_old, resolver_new,
            )
            if card is not None:
                routines.append(card)
    return LadderDocument(commit=commit, routines=routines)


def _build_routine(
    controller: Optional[str],
    program: str,
    routine: str,
    old_rt: Routine,
    new_rt: Routine,
    old_label: Optional[str],
    new_label: Optional[str],
    parser: RLLParser,
    resolver_old: LabelResolver,
    resolver_new: LabelResolver,
) -> Optional[RoutineLadderDiff]:
    rows = align_rungs(old_rt.content.rungs or [], new_rt.content.rungs or [], lambda: parser)
    rungs = [_build_rung(row, parser, resolver_old, resolver_new) for row in rows]
    if all(r.status == "unchanged" for r in rungs):
        return None  # the routine differs, but not in any rung the view shows
    return RoutineLadderDiff(
        controller=controller,
        program=program,
        routine=routine,
        routine_type="RLL",
        old_label=old_label,
        new_label=new_label,
        summary=_summarize(rungs),
        rungs=rungs,
    )


def _build_rung(
    row: RungRow,
    parser: RLLParser,
    resolver_old: LabelResolver,
    resolver_new: LabelResolver,
) -> RungDiff:
    old_rung, new_rung = row.old, row.new
    if row.status == "modified":
        old_parsed = _try_parse(old_rung.text, parser)
        new_parsed = _try_parse(new_rung.text, parser)
        if old_parsed is None or new_parsed is None:
            before = [Element(kind="raw", status="modified", text=old_rung.text or "")]
            after = [Element(kind="raw", status="modified", text=new_rung.text or "")]
        else:
            before, after = diff_rung_elements(old_parsed, new_parsed, resolver_old, resolver_new)
    elif row.status == "removed":
        before, after = _classify_text(old_rung.text, parser, resolver_old), []
    elif row.status == "added":
        before, after = [], _classify_text(new_rung.text, parser, resolver_new)
    else:  # unchanged or comment_changed — logic is identical on both sides
        before = _classify_text(old_rung.text, parser, resolver_old) if old_rung else []
        after = _classify_text(new_rung.text, parser, resolver_new) if new_rung else []
    # The diff above is aligned on the rung's true source order; only now, for
    # the side-by-side view, lay each side out reads-left / writes-right.
    before = order_io(before, resolver_old)
    after = order_io(after, resolver_new)
    return RungDiff(
        status=row.status,
        old_number=old_rung.number if old_rung else None,
        new_number=new_rung.number if new_rung else None,
        old_comment=old_rung.comment if old_rung else None,
        new_comment=new_rung.comment if new_rung else None,
        before=before,
        after=after,
    )


def _try_parse(text: Optional[str], parser: RLLParser) -> Optional[ParsedRung]:
    """Parse rung text, or None if it is empty or the grammar cannot read it."""
    if not text:
        return None
    try:
        return parser.parse(text)
    except Exception:
        return None


def _classify_text(text: Optional[str], parser: RLLParser, resolver: LabelResolver) -> list[Element]:
    """Classify a rung's text, falling back to a raw element it cannot parse."""
    parsed = _try_parse(text, parser)
    if parsed is None:
        return [Element(kind="raw", text=text)] if text else []
    return classify_rung(parsed, resolver)


def _summarize(rungs: list[RungDiff]) -> RoutineSummary:
    return RoutineSummary(
        rungs_modified=sum(1 for r in rungs if r.status == "modified"),
        rungs_added=sum(1 for r in rungs if r.status == "added"),
        rungs_removed=sum(1 for r in rungs if r.status == "removed"),
        additions=sum(_count_status(r.after, "added") for r in rungs),
        removals=sum(_count_status(r.before, "removed") for r in rungs),
    )


def _count_status(elements: list[Element], status: str) -> int:
    """Count leaf elements (not branches) carrying a status, recursing legs."""
    total = 0
    for el in elements:
        if el.kind == "branch":
            for leg in el.legs:
                total += _count_status(leg, status)
        elif el.status == status:
            total += 1
    return total
