"""Turn a ChangeSet into plain readable text."""
from __future__ import annotations

import json

from .models import (
    ChangeSet,
    EntityChange,
    FieldChange,
    LineChange,
    ProgramChange,
    RoutineChange,
    RungChange,
)

_TYPE_WORDS = {
    "RLL": "ladder",
    "ST": "structured text",
    "FBD": "function block",
    "SFC": "sequential function chart",
}

_MAX_VALUE = 120


def render_text(cs: ChangeSet) -> str:
    """One readable report of everything that changed."""
    if cs.is_empty():
        return "No differences found."

    lines: list[str] = [_summary(cs), ""]
    if cs.controller:
        lines.append("Controller:")
        lines.extend(_field_lines(cs.controller, indent=1))
    _entity_section(lines, "Modules", cs.modules)
    _entity_section(lines, "Data types", cs.data_types)
    _entity_section(lines, "AOIs", cs.add_on_instructions)
    _entity_section(lines, "Controller tags", cs.controller_tags)
    for program in cs.programs:
        _program_section(lines, program)
    _entity_section(lines, "Tasks", cs.tasks)
    return "\n".join(lines)


def _summary(cs: ChangeSet) -> str:
    parts = []
    if cs.controller:
        parts.append(_count(len(cs.controller), "controller setting"))
    if cs.modules:
        parts.append(_count(len(cs.modules), "module"))
    if cs.data_types:
        parts.append(_count(len(cs.data_types), "data type"))
    if cs.add_on_instructions:
        parts.append(_count(len(cs.add_on_instructions), "AOI"))
    if cs.controller_tags:
        parts.append(_count(len(cs.controller_tags), "controller tag"))
    if cs.programs:
        rungs = sum(len(r.rungs) for p in cs.programs for r in p.routines)
        st_lines = sum(len(r.lines) for p in cs.programs for r in p.routines)
        detail = []
        if rungs:
            detail.append(_count(rungs, "rung"))
        if st_lines:
            detail.append(_count(st_lines, "line"))
        text = _count(len(cs.programs), "program")
        if detail:
            text += f" ({', '.join(detail)})"
        parts.append(text)
    if cs.tasks:
        parts.append(_count(len(cs.tasks), "task"))
    return "Changes: " + ", ".join(parts)


def _count(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _entity_section(lines: list[str], title: str, changes: list[EntityChange]) -> None:
    if not changes:
        return
    lines.append(f"{title}:")
    for change in changes:
        if change.kind in ("added", "removed"):
            lines.append(f"  {change.kind}: {change.name}")
        else:
            lines.append(f"  {change.name}:")
            lines.extend(_field_lines(change.fields, indent=2))


def _program_section(lines: list[str], program: ProgramChange) -> None:
    if program.kind in ("added", "removed"):
        lines.append(f"Program {program.name}: {program.kind}")
        return
    lines.append(f"Program {program.name}:")
    lines.extend(_field_lines(program.fields, indent=1))
    if program.tags:
        lines.append("  Tags:")
        for tag in program.tags:
            if tag.kind in ("added", "removed"):
                lines.append(f"    {tag.kind}: {tag.name}")
            else:
                lines.append(f"    {tag.name}:")
                lines.extend(_field_lines(tag.fields, indent=3))
    for routine in program.routines:
        _routine_section(lines, routine)


def _routine_section(lines: list[str], routine: RoutineChange) -> None:
    type_word = _TYPE_WORDS.get(routine.routine_type or "", routine.routine_type or "")
    label = f"  Routine {routine.name}" + (f" ({type_word})" if type_word else "")
    if routine.kind in ("added", "removed"):
        lines.append(f"{label}: {routine.kind}")
        return
    lines.append(f"{label}:")
    lines.extend(_field_lines(routine.fields, indent=2))
    if routine.note:
        lines.append(f"    {routine.note}")
    if routine.formatting_only:
        lines.append("    formatting changed only (same logic)")
    for rung in routine.rungs:
        _rung_lines(lines, rung)
    for line in routine.lines:
        _line_lines(lines, line)


def _rung_lines(lines: list[str], rung: RungChange) -> None:
    if rung.kind == "added":
        lines.append(f"    rung {rung.new_number} added: {_value(rung.new_text)}")
    elif rung.kind == "removed":
        lines.append(f"    rung {rung.old_number} removed: {_value(rung.old_text)}")
    elif rung.kind == "comment_changed":
        lines.append(f"    rung {rung.new_number} comment changed")
        lines.append(f"      was: {_value(rung.old_comment)}")
        lines.append(f"      now: {_value(rung.new_comment)}")
    else:
        lines.append(f"    rung {rung.new_number} changed")
        if rung.old_text or rung.new_text:
            lines.append(f"      was: {_value(rung.old_text)}")
            lines.append(f"      now: {_value(rung.new_text)}")
        else:  # a comment rung — its content is the comment
            lines.append(f"      was: {_value(rung.old_comment)}")
            lines.append(f"      now: {_value(rung.new_comment)}")


def _line_lines(lines: list[str], line: LineChange) -> None:
    if line.kind == "added":
        lines.append(f"    line {line.new_number} added: {_value(line.new_text)}")
    elif line.kind == "removed":
        lines.append(f"    line {line.old_number} removed: {_value(line.old_text)}")
    else:
        lines.append(f"    line {line.new_number} changed")
        lines.append(f"      was: {_value(line.old_text)}")
        lines.append(f"      now: {_value(line.new_text)}")


def _field_lines(fields: list[FieldChange], indent: int) -> list[str]:
    pad = "  " * indent
    return [
        f"{pad}{f.path}: {_value(f.old)} -> {_value(f.new)}"
        for f in fields
    ]


def _value(value: object) -> str:
    """Show one value on a single readable line.

    Missing values say "(not set)" instead of None, anything that is not
    text becomes JSON, and long values are cut off so one big tag value
    cannot flood the report.
    """
    if value is None:
        return "(not set)"
    if isinstance(value, str):
        text = value.strip()
    else:
        text = json.dumps(value, ensure_ascii=False)
    if len(text) > _MAX_VALUE:
        text = text[: _MAX_VALUE - 3] + "..."
    return text
