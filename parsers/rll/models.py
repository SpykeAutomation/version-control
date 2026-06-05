"""
AST models for parsed RLL (Relay Ladder Logic) rung text.

The tree mirrors the rung structure:
  ParsedRung
    ├── RLLInstruction  (name + operands)
    └── RLLBranch       (parallel legs, each a list of nodes)
"""
from __future__ import annotations

from typing import Union

from pydantic import BaseModel


class RLLParam(BaseModel):
    """A single operand/parameter of an RLL instruction.

    Stores the individual tokens that make up the parameter.
    For simple operands (a single tag name), tokens has one element.
    For complex operands (I/O paths, expressions), tokens has many.
    Empty parameters (e.g. GSV(Class,,Attr,Dest)) have an empty list.
    """

    tokens: list[str] = []

    @property
    def is_empty(self) -> bool:
        return len(self.tokens) == 0

    @property
    def text(self) -> str:
        """Reconstruct the parameter text from tokens.

        Joins with no separator by default, inserting a space only between
        two 'word' tokens (identifiers, numbers, keywords).
        """
        if not self.tokens:
            return ""
        parts: list[str] = [self.tokens[0]]
        for prev, curr in zip(self.tokens, self.tokens[1:]):
            if _is_word(prev) and _is_word(curr):
                parts.append(" ")
            parts.append(curr)
        return "".join(parts)


class RLLInstruction(BaseModel):
    """A single instruction within an RLL rung."""

    name: str
    params: list[RLLParam] = []


class RLLBranch(BaseModel):
    """A parallel branch group: ``[leg1 ,leg2 ,leg3]``.

    Each leg is a list of RLLNode (instructions and/or nested branches).
    """

    legs: list[list[RLLNode]] = []


# Union of possible node types in the rung tree
RLLNode = Union[RLLInstruction, RLLBranch]

# Pydantic needs to resolve the forward reference after both classes exist
RLLBranch.model_rebuild()


class ParsedRung(BaseModel):
    """The full AST for one parsed RLL rung."""

    elements: list[RLLNode] = []


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _is_word(token: str) -> bool:
    """True if the token starts with a letter, digit, or underscore."""
    return bool(token) and (token[0].isalpha() or token[0].isdigit() or token[0] == "_")
