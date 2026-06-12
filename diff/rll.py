"""Rung matching for ladder routines.

Rung numbers shift whenever a rung is inserted or deleted, so comparing
rung 3 to rung 3 reports false changes for every rung below the insert.
This module matches rungs by content instead: a renumbered rung is not a
change, an inserted rung is exactly one added rung, and an edited rung is
paired with its old self by text similarity.
"""
from __future__ import annotations

import difflib
from typing import Callable

from parsers.l5x.models import Rung
from parsers.rll import RLLParser

from .models import RungChange

# Two rungs whose text is at least this similar count as one edited rung
# rather than one removed plus one added.
_SIMILAR = 0.6

# Cross-pairing every old rung with every new rung is quadratic; above this
# block size fall back to pairing by position. Real edit blocks are small.
_PAIRING_LIMIT = 10_000


def diff_rungs(
    old: list[Rung],
    new: list[Rung],
    get_parser: Callable[[], RLLParser],
) -> list[RungChange]:
    """Compare two rung lists and report only real changes.

    `get_parser` supplies an RLLParser on demand; it is only called when an
    edited rung pair needs a formatting check, so unchanged routines never
    pay for grammar work.
    """
    if old == new:
        return []

    old_keys = [_content_key(r) for r in old]
    new_keys = [_content_key(r) for r in new]
    # autojunk must stay off: routines legally repeat rungs (NOP();, JSR
    # patterns), and autojunk would discard repeated entries as noise.
    matcher = difflib.SequenceMatcher(None, old_keys, new_keys, autojunk=False)

    changes: list[RungChange] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            for o, n in zip(old[i1:i2], new[j1:j2]):
                if _comment(o) != _comment(n):
                    changes.append(_comment_change(o, n))
        elif op == "delete":
            changes.extend(_removed(r) for r in old[i1:i2])
        elif op == "insert":
            changes.extend(_added(r) for r in new[j1:j2])
        else:  # replace
            changes.extend(_pair_block(old[i1:i2], new[j1:j2], get_parser))
    return changes


def _content_key(rung: Rung) -> tuple[str, str]:
    """What a rung says, ignoring its number.

    For a comment rung (type C) the comment is the content. For a normal
    rung the comment is left out, so a comment edit still matches the rung
    and reports as comment_changed instead of a logic change.
    """
    if (rung.type or "N") == "C":
        return ("C", _comment(rung))
    return ("N", (rung.text or "").strip())


def _comment(rung: Rung) -> str:
    return (rung.comment or "").strip()


def _pair_block(
    old_block: list[Rung],
    new_block: list[Rung],
    get_parser: Callable[[], RLLParser],
) -> list[RungChange]:
    """Pair up the rungs inside one disagreeing stretch.

    Most-similar pairs become edits; whatever finds no partner is a plain
    removal or addition.
    """
    if len(old_block) * len(new_block) > _PAIRING_LIMIT:
        pairs = list(zip(range(len(old_block)), range(len(new_block))))
        used_old = set(range(min(len(old_block), len(new_block))))
        used_new = set(used_old)
    else:
        candidates = []
        for oi, o in enumerate(old_block):
            for ni, n in enumerate(new_block):
                if _content_key(o)[0] != _content_key(n)[0]:
                    continue  # never pair a comment rung with a logic rung
                ratio = _similarity(_content_key(o)[1], _content_key(n)[1])
                if ratio >= _SIMILAR:
                    candidates.append((-ratio, oi, ni))
        candidates.sort()
        pairs, used_old, used_new = [], set(), set()
        for _, oi, ni in candidates:
            if oi not in used_old and ni not in used_new:
                pairs.append((oi, ni))
                used_old.add(oi)
                used_new.add(ni)

    changes: list[RungChange] = []
    for oi, ni in pairs:
        changes.extend(_pair_change(old_block[oi], new_block[ni], get_parser))
    changes.extend(_removed(o) for i, o in enumerate(old_block) if i not in used_old)
    changes.extend(_added(n) for i, n in enumerate(new_block) if i not in used_new)
    changes.sort(key=lambda c: (c.new_number if c.new_number is not None else c.old_number or 0))
    return changes


def _similarity(a: str, b: str) -> float:
    """How alike two rung texts are, from 0 (nothing shared) to 1 (equal).

    The exact score is costly to compute, so two fast estimates run first;
    if either already says the pair can't reach the pairing threshold, the
    pair is rejected without doing the expensive comparison.
    """
    sm = difflib.SequenceMatcher(None, a, b)
    if sm.real_quick_ratio() < _SIMILAR or sm.quick_ratio() < _SIMILAR:
        return 0.0
    return sm.ratio()


def _pair_change(
    old: Rung,
    new: Rung,
    get_parser: Callable[[], RLLParser],
) -> list[RungChange]:
    """Describe one old/new rung pair that the matcher decided is an edit.

    Returns the change to report, or nothing when the difference turns out
    to be cosmetic: if both texts parse to the same logic, only the spacing
    moved, and that is not worth an engineer's attention.
    """
    if (old.type or "N") == "C":
        # A comment rung's content is its comment text.
        return [
            RungChange(
                kind="modified",
                old_number=old.number,
                new_number=new.number,
                old_comment=_comment(old),
                new_comment=_comment(new),
            )
        ]

    if _logic_equal(old.text, new.text, get_parser):
        if _comment(old) != _comment(new):
            return [_comment_change(old, new)]
        return []  # spacing only — not a real change

    return [
        RungChange(
            kind="modified",
            old_number=old.number,
            new_number=new.number,
            old_text=old.text,
            new_text=new.text,
            old_comment=old.comment,
            new_comment=new.comment,
        )
    ]


def _logic_equal(
    old_text: str | None,
    new_text: str | None,
    get_parser: Callable[[], RLLParser],
) -> bool:
    """True when both texts parse to the same logic tree."""
    if not old_text or not new_text:
        return False
    try:
        parser = get_parser()
        return parser.parse(old_text) == parser.parse(new_text)
    except Exception:
        # A rung the grammar cannot read still diffs — just by raw text.
        return False


def _comment_change(old: Rung, new: Rung) -> RungChange:
    return RungChange(
        kind="comment_changed",
        old_number=old.number,
        new_number=new.number,
        old_comment=old.comment,
        new_comment=new.comment,
    )


def _removed(rung: Rung) -> RungChange:
    return RungChange(
        kind="removed",
        old_number=rung.number,
        old_text=rung.text,
        old_comment=rung.comment,
    )


def _added(rung: Rung) -> RungChange:
    return RungChange(
        kind="added",
        new_number=rung.number,
        new_text=rung.text,
        new_comment=rung.comment,
    )
