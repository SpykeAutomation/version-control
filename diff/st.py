"""Line matching for structured-text routines."""
from __future__ import annotations

import difflib
from typing import Callable

from parsers.l5x.models import STLine
from parsers.st import STParser

from .models import LineChange


def diff_st_lines(
    old: list[STLine],
    new: list[STLine],
    get_parser: Callable[[], STParser],
) -> tuple[list[LineChange], bool]:
    """Compare two ST routines line by line.

    Returns (changes, formatting_only). When the two texts parse to the
    same logic (spacing or keyword case moved around), no line changes are
    reported and formatting_only is True.
    """
    if old == new:
        return [], False

    old_texts = [line.text for line in old]
    new_texts = [line.text for line in new]
    if _logic_equal(old_texts, new_texts, get_parser):
        return [], True

    matcher = difflib.SequenceMatcher(
        None,
        [t.strip() for t in old_texts],
        [t.strip() for t in new_texts],
        autojunk=False,
    )
    changes: list[LineChange] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        if op in ("delete", "replace"):
            removed = old[i1:i2]
        else:
            removed = []
        if op in ("insert", "replace"):
            added = new[j1:j2]
        else:
            added = []
        if op == "replace":
            # A replace block means N old lines were overwritten by M new
            # ones. Lines that sit opposite each other count as one edited
            # line, not a removal plus an addition; the slicing below keeps
            # whatever has no opposite (when N and M differ) and reports
            # those as plain removals or additions.
            for o, n in zip(removed, added):
                changes.append(
                    LineChange(
                        kind="modified",
                        old_number=o.number,
                        new_number=n.number,
                        old_text=o.text,
                        new_text=n.text,
                    )
                )
            removed = removed[len(added):]
            added = added[len(old[i1:i2]):]
        changes.extend(
            LineChange(kind="removed", old_number=o.number, old_text=o.text)
            for o in removed
        )
        changes.extend(
            LineChange(kind="added", new_number=n.number, new_text=n.text)
            for n in added
        )
    return changes, False


def _logic_equal(
    old_texts: list[str],
    new_texts: list[str],
    get_parser: Callable[[], STParser],
) -> bool:
    """True when both routines parse to the same statements."""
    try:
        parser = get_parser()
        return parser.parse_lines(old_texts) == parser.parse_lines(new_texts)
    except Exception:
        return False
