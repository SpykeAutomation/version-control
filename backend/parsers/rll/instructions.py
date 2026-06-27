"""Built-in RLL instruction reference: how each instruction draws in ladder
and what its operands are called.

The data lives in ``instructions.json`` (reference data, not code) so the set
can grow without touching logic; this module just loads and caches it. Each
entry gives a ``display`` ("contact" | "coil" | "box"), a ``form`` (contact:
"no"/"nc"; coil: "ote"/"otl"/"otu"; else null), a ``role`` ("input" for
condition instructions that read — contacts and the compare/test boxes;
"output" for instructions that act — coils and the rest), and, for boxes, the
ordered ``operands`` label list. The role lets a rung draw its reads on the
left and its writes on the right, the way ladder logic is laid out.

Operand labels and glyphs were pulled from the Rockwell Automation reference
manuals: Logix 5000 General Instructions (publication 1756-RM003), Advanced
Process Control and Drives Instructions (1756-RM006), Motion Instructions
(MOTION-RM002), and GuardLogix Safety Instructions (1756-RM095).

This covers the built-in instruction set only. User-defined AOIs are resolved
per project from the parsed AOI definition, not from here; an unknown mnemonic
falls back to a generic box with positional, unlabeled operands.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATA_PATH = Path(__file__).parent / "instructions.json"


@lru_cache(maxsize=1)
def instruction_table() -> dict[str, dict]:
    """Mapping of instruction mnemonic to its display spec. Loaded once.

    The returned dict is shared and treated as read-only; callers must not
    mutate it.
    """
    data = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    return data["instructions"]
