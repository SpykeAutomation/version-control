"""
RLL rung text parser — converts raw rung strings into a structured AST.

Uses a Lark LALR grammar to parse, then transforms the Lark tree into
the Pydantic models defined in ``parsers.rll.models``.

Usage
-----
    from parsers.rll import RLLParser

    parser = RLLParser()                    # loads grammar once
    rung   = parser.parse("XIC(A)OTE(B);") # returns ParsedRung
"""
from __future__ import annotations

from pathlib import Path

from lark import Lark, Token, Transformer, Tree
from lark.exceptions import LarkError

from .models import ParsedRung, RLLBranch, RLLInstruction, RLLParam

_GRAMMAR_PATH = Path(__file__).parent / "grammar.lark"


class _RLLTransformer(Transformer):
    """Bottom-up transformer: Lark Tree → Pydantic AST models."""

    # --- top-level ---

    def start(self, items: list) -> ParsedRung:
        elements = [i for i in items if isinstance(i, (RLLInstruction, RLLBranch))]
        return ParsedRung(elements=elements)

    # --- instructions ---

    def instruction(self, items: list) -> RLLInstruction:
        name = str(items[0])
        params: list[RLLParam] = items[1] if len(items) > 1 and items[1] is not None else []
        return RLLInstruction(name=name, params=params)

    def param_list(self, items: list) -> list[RLLParam]:
        return list(items)

    def param_expr(self, items: list) -> RLLParam:
        return RLLParam(tokens=_flatten(items))

    def empty_param(self, _items: list) -> RLLParam:
        return RLLParam(tokens=[])

    # --- branches ---

    def branch(self, items: list) -> RLLBranch:
        return RLLBranch(legs=list(items))

    def leg(self, items: list) -> list:
        return list(items)

    # --- sub-expressions inside parameters ---

    def paren_group(self, items: list) -> list[str]:
        tokens = ["("]
        tokens.extend(_flatten(items))
        tokens.append(")")
        return tokens

    def subscript(self, items: list) -> list[str]:
        tokens = ["["]
        for i, item in enumerate(items):
            if i > 0:
                tokens.append(",")
            if isinstance(item, list):
                tokens.extend(item)
        tokens.append("]")
        return tokens

    def subscript_dim(self, items: list) -> list[str]:
        return _flatten(items)


def _flatten(items: list) -> list[str]:
    """Flatten a mixed list of Tokens, strings, and nested lists into a
    flat list of string values."""
    result: list[str] = []
    for item in items:
        if isinstance(item, Token):
            result.append(str(item))
        elif isinstance(item, str):
            result.append(item)
        elif isinstance(item, list):
            result.extend(item)
        elif isinstance(item, Tree):
            result.extend(_flatten(item.children))
    return result


class RLLParser:
    """Reusable RLL rung text parser.

    Loads the grammar once at construction and reuses it for every
    ``parse()`` call.  Thread-safe for concurrent reads once constructed.
    """

    def __init__(self) -> None:
        grammar_text = _GRAMMAR_PATH.read_text(encoding="utf-8")
        self._lark = Lark(
            grammar_text,
            parser="lalr",
            transformer=_RLLTransformer(),
        )

    def parse(self, rung_text: str) -> ParsedRung:
        """Parse a single rung text string and return a ``ParsedRung``.

        Returns an empty ParsedRung for None/empty/whitespace-only input.
        Raises ``RLLParseError`` if the text cannot be parsed.
        """
        if not rung_text or not rung_text.strip():
            return ParsedRung()

        try:
            result = self._lark.parse(rung_text)
        except LarkError as exc:
            raise RLLParseError(rung_text, exc) from exc

        # When transformer is passed to Lark constructor, parse() returns
        # the transformer's start() result directly (a ParsedRung).
        if isinstance(result, ParsedRung):
            return result

        # Fallback: should not happen, but be defensive.
        return ParsedRung()  # pragma: no cover


class RLLParseError(Exception):
    """Raised when a rung text string cannot be parsed."""

    def __init__(self, rung_text: str, cause: Exception) -> None:
        self.rung_text = rung_text
        self.cause = cause
        # Show first 120 chars of the rung in the error message
        preview = rung_text[:120] + ("..." if len(rung_text) > 120 else "")
        super().__init__(f"Failed to parse RLL rung: {preview!r}\n  Cause: {cause}")
