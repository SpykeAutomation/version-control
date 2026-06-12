"""Compare two parsed projects and produce a ChangeSet."""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from parsers.l5x.models import L5XDocument, Program, Routine
from parsers.rll import RLLParser
from parsers.st import STParser

from .fields import diff_fields
from .models import ChangeSet, EntityChange, ProgramChange, RoutineChange
from .rll import diff_rungs
from .st import diff_st_lines

# The export timestamp changes on every export and is not project content
# (same policy as snapshots, which drop it entirely).
_METADATA_EXCLUDE = frozenset({"export_date"})


@lru_cache(maxsize=None)
def _default_rll() -> RLLParser:
    return RLLParser()


@lru_cache(maxsize=None)
def _default_st() -> STParser:
    return STParser()


def diff_documents(
    old: L5XDocument,
    new: L5XDocument,
    *,
    rll_parser: Optional[RLLParser] = None,
    st_parser: Optional[STParser] = None,
) -> ChangeSet:
    """Everything that differs between two versions of a project.

    The optional parser arguments let callers (and tests) supply already
    built parsers; otherwise one of each is built lazily, and only if some
    changed routine actually needs it.
    """
    get_rll = (lambda: rll_parser) if rll_parser is not None else _default_rll
    get_st = (lambda: st_parser) if st_parser is not None else _default_st

    return ChangeSet(
        controller=[
            *diff_fields(
                old.metadata.model_dump(mode="json"),
                new.metadata.model_dump(mode="json"),
                exclude=_METADATA_EXCLUDE,
                prefix="metadata",
            ),
            *diff_fields(
                old.controller.model_dump(mode="json"),
                new.controller.model_dump(mode="json"),
                prefix="controller",
            ),
        ],
        modules=diff_named(old.modules, new.modules),
        data_types=diff_named(old.data_types, new.data_types),
        add_on_instructions=diff_named(old.add_on_instructions, new.add_on_instructions),
        controller_tags=diff_named(old.controller_tags, new.controller_tags),
        programs=_diff_programs(old.programs, new.programs, get_rll, get_st),
        tasks=diff_named(old.tasks, new.tasks),
    )


def diff_named(old_list, new_list, exclude: frozenset[str] = frozenset()) -> list[EntityChange]:
    """Match two lists of named entities by name and report the differences."""
    olds = {e.name: e for e in old_list}
    news = {e.name: e for e in new_list}
    changes: list[EntityChange] = []
    for name in sorted(olds.keys() | news.keys()):
        if name not in news:
            changes.append(EntityChange(name=name, kind="removed"))
        elif name not in olds:
            changes.append(EntityChange(name=name, kind="added"))
        elif olds[name] != news[name]:
            fields = diff_fields(
                olds[name].model_dump(mode="json"),
                news[name].model_dump(mode="json"),
                exclude=exclude,
            )
            if fields:
                changes.append(EntityChange(name=name, kind="modified", fields=fields))
    return changes


def _diff_programs(old_list, new_list, get_rll, get_st) -> list[ProgramChange]:
    """Match programs by name and describe each one that differs.

    A modified program reports three things: its own settings, its tags,
    and its routines. Programs that are equal are skipped without looking
    inside them.
    """
    olds = {p.name: p for p in old_list}
    news = {p.name: p for p in new_list}
    changes: list[ProgramChange] = []
    for name in sorted(olds.keys() | news.keys()):
        if name not in news:
            changes.append(ProgramChange(name=name, kind="removed"))
            continue
        if name not in olds:
            changes.append(ProgramChange(name=name, kind="added"))
            continue
        o, n = olds[name], news[name]
        if o == n:
            continue
        change = ProgramChange(
            name=name,
            kind="modified",
            fields=diff_fields(
                o.model_dump(mode="json", exclude={"tags", "routines"}),
                n.model_dump(mode="json", exclude={"tags", "routines"}),
            ),
            tags=diff_named(o.tags, n.tags),
            routines=_diff_routines(o, n, get_rll, get_st),
        )
        if change.fields or change.tags or change.routines:
            changes.append(change)
    return changes


def _diff_routines(old_prog: Program, new_prog: Program, get_rll, get_st) -> list[RoutineChange]:
    """Match a program's routines by name and describe each one that differs.

    A change that turns out to be nothing real (for example rungs that only
    got renumbered) produces no entry at all.
    """
    olds = {r.name: r for r in old_prog.routines}
    news = {r.name: r for r in new_prog.routines}
    changes: list[RoutineChange] = []
    for name in sorted(olds.keys() | news.keys()):
        if name not in news:
            changes.append(
                RoutineChange(name=name, kind="removed", routine_type=olds[name].type)
            )
            continue
        if name not in olds:
            changes.append(
                RoutineChange(name=name, kind="added", routine_type=news[name].type)
            )
            continue
        o, n = olds[name], news[name]
        if o == n:
            continue
        change = _diff_one_routine(name, o, n, get_rll, get_st)
        if (
            change.fields
            or change.rungs
            or change.lines
            or change.note
            or change.formatting_only
        ):
            changes.append(change)
    return changes


def _diff_one_routine(name: str, o: Routine, n: Routine, get_rll, get_st) -> RoutineChange:
    """Describe one changed routine in the right way for its kind.

    Ladder routines get rung matching, structured text gets line matching,
    FBD/SFC (not parsed yet) just say they changed, and protected routines
    can only be compared by their visible settings.
    """
    change = RoutineChange(name=name, kind="modified", routine_type=n.type)
    change.fields = diff_fields(
        o.model_dump(mode="json", exclude={"content"}),
        n.model_dump(mode="json", exclude={"content"}),
    )

    if o.type != n.type:
        change.note = "content replaced (routine type changed)"
    elif o.encoded or n.encoded:
        # Protected content is never exported readably; the metadata fields
        # (already in change.fields) are all there is to compare.
        pass
    elif n.type == "RLL":
        change.rungs = diff_rungs(o.content.rungs or [], n.content.rungs or [], get_rll)
    elif n.type == "ST":
        change.lines, change.formatting_only = diff_st_lines(
            o.content.lines or [], n.content.lines or [], get_st
        )
    elif o.content.raw_xml != n.content.raw_xml:
        change.note = "changed (not yet parsed)"
    return change
