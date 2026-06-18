"""Turn parsed ladder logic into drawable elements (the ladder-diff IR).

The parser says *what is written* (an instruction name and its operand
tokens); the instruction reference says *what it means* (a glyph and operand
labels). ``classify`` joins the two into one ``Element`` the renderer can draw.

This module only answers "what does this instruction look like?" — there is no
diff here. Element status stays the default ("unchanged"); the element-level
diff fills it in later.
"""
from __future__ import annotations

from typing import Optional

from parsers.rll.instructions import instruction_table
from parsers.rll.models import ParsedRung, RLLBranch, RLLInstruction, RLLNode

from .ladder_models import Element, Operand


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
            return {"display": "box", "form": None, "operands": labels}
        return None


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
