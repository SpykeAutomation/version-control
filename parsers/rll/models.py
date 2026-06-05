"""
AST models for parsed RLL (Relay Ladder Logic) rung text.

The tree mirrors the rung structure:
  ParsedRung
    ├── RLLInstruction  (name + operands)
    └── RLLBranch       (parallel legs, each a list of nodes)

Helper methods on ParsedRung flatten the tree for common checker queries
like "find all instructions named JSR in this rung."
"""
from __future__ import annotations

from typing import Optional, Union

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

    def all_instructions(self) -> list[RLLInstruction]:
        """Return every instruction in this rung, flattened from branches."""
        result: list[RLLInstruction] = []
        _collect_instructions(self.elements, result)
        return result

    def has_instruction(self, name: str) -> bool:
        """Check whether an instruction with the given name exists."""
        return any(i.name == name for i in self.all_instructions())

    def find_instructions(self, name: str) -> list[RLLInstruction]:
        """Return all instructions matching the given name."""
        return [i for i in self.all_instructions() if i.name == name]

    def first_instruction(self) -> Optional[RLLInstruction]:
        """Return the first instruction in series order (first element,
        or first instruction of the first leg of a leading branch)."""
        return _first_instruction(self.elements)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _is_word(token: str) -> bool:
    """True if the token starts with a letter, digit, or underscore."""
    return bool(token) and (token[0].isalpha() or token[0].isdigit() or token[0] == "_")


def _collect_instructions(nodes: list[RLLNode], out: list[RLLInstruction]) -> None:
    for node in nodes:
        if isinstance(node, RLLInstruction):
            out.append(node)
        elif isinstance(node, RLLBranch):
            for leg in node.legs:
                _collect_instructions(leg, out)


def _first_instruction(nodes: list[RLLNode]) -> Optional[RLLInstruction]:
    for node in nodes:
        if isinstance(node, RLLInstruction):
            return node
        if isinstance(node, RLLBranch) and node.legs:
            result = _first_instruction(node.legs[0])
            if result is not None:
                return result
    return None
