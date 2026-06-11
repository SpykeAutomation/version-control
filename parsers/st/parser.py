"""
ST routine text parser — converts raw Structured Text into a structured AST.

Uses a Lark LALR grammar to parse, then walks the Lark tree to extract
the information needed by the analysis engine.

Usage
-----
    from parsers.st import STParser

    parser = STParser()                              # loads grammar once
    result = parser.parse("tag := 100;")             # returns ParsedST
    result = parser.parse_lines(["tag := 100;"])     # same, from line list
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from lark import Lark, Token, Tree
from lark.exceptions import LarkError

from .models import ParsedST, STAssignment, STCall, STStatement

_GRAMMAR_PATH = Path(__file__).parent / "grammar.lark"

# Tree names that represent statements (mirrors ?statement in grammar.lark)
_STMT_TYPES = (
    "if_stmt", "for_stmt", "while_stmt", "repeat_stmt",
    "case_stmt", "assign_stmt", "call_stmt", "expr_stmt",
    "exit_stmt", "return_stmt",
)


class _STTreeVisitor:
    """Walk a Lark parse tree and produce STStatement / STCall nodes."""

    def visit_start(self, tree: Tree) -> list[STStatement]:
        return [self._visit_stmt(child) for child in tree.children
                if isinstance(child, Tree)]

    def _visit_stmt(self, tree: Tree) -> STStatement:
        handler = getattr(self, f"_visit_{tree.data}", None)
        if handler:
            return handler(tree)
        # Fallback for unknown statement types
        return STStatement(kind=tree.data, nested_calls=self._find_calls(tree))

    def _visit_assign_stmt(self, tree: Tree) -> STStatement:
        target = _reconstruct_expr(tree.children[0])
        value = _reconstruct_expr(tree.children[2])  # skip ASSIGN token
        calls = self._find_calls(tree)
        return STStatement(
            kind="assign",
            assignment=STAssignment(target=target, value=value),
            nested_calls=calls,
        )

    def _visit_call_stmt(self, tree: Tree) -> STStatement:
        call_tree = tree.children[0]  # call_expr
        call = self._extract_call(call_tree)
        return STStatement(kind="call", call=call)

    def _visit_expr_stmt(self, tree: Tree) -> STStatement:
        calls = self._find_calls(tree)
        return STStatement(kind="expr", nested_calls=calls)

    def _visit_if_stmt(self, tree: Tree) -> STStatement:
        children: list[STStatement] = []
        calls = self._find_calls_shallow(tree)

        # Extract condition between IF and THEN tokens
        condition = None
        tc = tree.children
        if_idx = then_idx = None
        for i, c in enumerate(tc):
            if isinstance(c, Token):
                if c.type == "IF" and if_idx is None:
                    if_idx = i
                elif c.type == "THEN" and then_idx is None:
                    then_idx = i
        if if_idx is not None and then_idx is not None and then_idx > if_idx + 1:
            condition = _reconstruct_expr(tc[if_idx + 1])

        for child in tree.children:
            if isinstance(child, Tree) and child.data in _STMT_TYPES + (
                "elsif_clause", "else_clause",
            ):
                children.append(self._visit_stmt(child))
        return STStatement(kind="if", children=children, nested_calls=calls, condition=condition)

    def _visit_elsif_clause(self, tree: Tree) -> STStatement:
        children = self._visit_body_stmts(tree)
        calls = self._find_calls_shallow(tree)

        # Extract condition between ELSIF and THEN tokens
        condition = None
        tc = tree.children
        elsif_idx = then_idx = None
        for i, c in enumerate(tc):
            if isinstance(c, Token):
                if c.type == "ELSIF" and elsif_idx is None:
                    elsif_idx = i
                elif c.type == "THEN" and then_idx is None:
                    then_idx = i
        if elsif_idx is not None and then_idx is not None and then_idx > elsif_idx + 1:
            condition = _reconstruct_expr(tc[elsif_idx + 1])

        return STStatement(kind="elsif", children=children, nested_calls=calls, condition=condition)

    def _visit_else_clause(self, tree: Tree) -> STStatement:
        children = self._visit_body_stmts(tree)
        return STStatement(kind="else", children=children)

    def _visit_for_stmt(self, tree: Tree) -> STStatement:
        children = self._visit_body_stmts(tree)
        calls = self._find_calls_shallow(tree)

        # for_stmt: FOR expr ASSIGN expr TO expr by_clause? DO stmts END_FOR ";"
        # ?-inlined simple exprs appear as bare Tokens, so extract by keyword
        # position rather than by fixed child index.
        loop_var = loop_start = loop_end = loop_step = None
        tc = tree.children
        # Find positions of keyword tokens
        assign_idx = to_idx = do_idx = None
        for i, c in enumerate(tc):
            if isinstance(c, Token):
                if c.type == "ASSIGN" and assign_idx is None:
                    assign_idx = i
                elif c.type == "TO" and to_idx is None:
                    to_idx = i
                elif c.type == "DO" and do_idx is None:
                    do_idx = i

        if assign_idx is not None and assign_idx >= 2:
            loop_var = _reconstruct_expr(tc[assign_idx - 1])
        if assign_idx is not None and to_idx is not None and to_idx > assign_idx + 1:
            loop_start = _reconstruct_expr(tc[assign_idx + 1])
        if to_idx is not None and do_idx is not None and do_idx > to_idx + 1:
            # The expression right after TO — could be followed by by_clause
            loop_end = _reconstruct_expr(tc[to_idx + 1])

        # Check for BY clause
        for c in tc:
            if isinstance(c, Tree) and str(getattr(c, "data", "")) == "by_clause":
                # by_clause children: BY(token), expr
                for bc in c.children:
                    if not (isinstance(bc, Token) and bc.type == "BY"):
                        loop_step = _reconstruct_expr(bc)
                        break
                break

        # Build readable header
        header = f"FOR {loop_var} := {loop_start} TO {loop_end}"
        if loop_step:
            header += f" BY {loop_step}"

        iteration_bound = _try_compute_iteration_bound(
            loop_start, loop_end, loop_step)

        has_exit = _has_exit_statement(children)

        return STStatement(
            kind="for", children=children, nested_calls=calls,
            loop_header=header, loop_var=loop_var,
            loop_start=loop_start, loop_end=loop_end, loop_step=loop_step,
            iteration_bound=iteration_bound, has_exit=has_exit,
        )

    def _visit_while_stmt(self, tree: Tree) -> STStatement:
        children = self._visit_body_stmts(tree)
        calls = self._find_calls_shallow(tree)

        # while_stmt: WHILE expr DO statement* END_WHILE ";"
        # Condition is between WHILE and DO tokens
        condition = None
        tc = tree.children
        while_idx = do_idx = None
        for i, c in enumerate(tc):
            if isinstance(c, Token):
                if c.type == "WHILE" and while_idx is None:
                    while_idx = i
                elif c.type == "DO" and do_idx is None:
                    do_idx = i

        if while_idx is not None and do_idx is not None and do_idx > while_idx + 1:
            condition = _reconstruct_expr(tc[while_idx + 1])

        header = f"WHILE {condition}" if condition else "WHILE ?"
        has_exit = _has_exit_statement(children)

        return STStatement(
            kind="while", children=children, nested_calls=calls,
            loop_header=header, has_exit=has_exit, condition=condition,
        )

    def _visit_repeat_stmt(self, tree: Tree) -> STStatement:
        children = self._visit_body_stmts(tree)
        calls = self._find_calls_shallow(tree)

        # repeat_stmt: REPEAT statement* UNTIL expr ";" END_REPEAT ";"
        # Condition is between UNTIL and END_REPEAT tokens
        condition = None
        tc = tree.children
        until_idx = end_idx = None
        for i, c in enumerate(tc):
            if isinstance(c, Token):
                if c.type == "UNTIL" and until_idx is None:
                    until_idx = i
                elif c.type == "END_REPEAT" and end_idx is None:
                    end_idx = i

        if until_idx is not None and end_idx is not None and end_idx > until_idx + 1:
            condition = _reconstruct_expr(tc[until_idx + 1])

        header = f"REPEAT UNTIL {condition}" if condition else "REPEAT UNTIL ?"
        has_exit = _has_exit_statement(children)

        return STStatement(
            kind="repeat", children=children, nested_calls=calls,
            loop_header=header, has_exit=has_exit, condition=condition,
        )

    def _visit_case_stmt(self, tree: Tree) -> STStatement:
        # The grammar parses labels and branch statements as a flat sequence
        # (see case_stmt in grammar.lark); regroup them into branches here.
        # Each case_labels node starts a new branch; the statements that
        # follow it belong to that branch.
        children: list[STStatement] = []
        branch: Optional[STStatement] = None
        for child in tree.children:
            if not isinstance(child, Tree):
                continue
            if child.data == "case_labels":
                branch = STStatement(kind="case_branch", children=[])
                children.append(branch)
            elif child.data == "else_clause":
                children.append(self._visit_else_clause(child))
                branch = None
            elif child.data in _STMT_TYPES and branch is not None:
                branch.children.append(self._visit_stmt(child))
        calls = self._find_calls_shallow(tree)
        return STStatement(kind="case", children=children, nested_calls=calls)

    def _visit_exit_stmt(self, _tree: Tree) -> STStatement:
        return STStatement(kind="exit")

    def _visit_return_stmt(self, _tree: Tree) -> STStatement:
        return STStatement(kind="return")

    def _visit_body_stmts(self, tree: Tree) -> list[STStatement]:
        """Extract child statements from a compound statement body."""
        result: list[STStatement] = []
        for child in tree.children:
            if isinstance(child, Tree) and child.data in _STMT_TYPES:
                result.append(self._visit_stmt(child))
        return result

    def _extract_call(self, tree: Tree) -> STCall:
        """Extract an STCall from a call_expr tree node."""
        name = str(tree.children[0])
        args: list[Optional[str]] = []
        for child in tree.children[1:]:
            if isinstance(child, Tree):
                if child.data == "call_args":
                    args = self._extract_call_args(child)
                elif child.data == "call_arg_expr":
                    args.append(_reconstruct_expr(child))
                elif child.data == "call_arg_empty":
                    args.append(None)
        return STCall(name=name, args=args)

    def _extract_call_args(self, tree: Tree) -> list[Optional[str]]:
        args: list[Optional[str]] = []
        for child in tree.children:
            if isinstance(child, Tree):
                if child.data == "call_arg_expr":
                    args.append(_reconstruct_expr(child))
                elif child.data == "call_arg_empty":
                    args.append(None)
        return args

    def _find_calls(self, tree: Tree) -> list[STCall]:
        """Find all call_expr nodes anywhere in the tree."""
        calls: list[STCall] = []
        self._walk_for_calls(tree, calls)
        return calls

    def _find_calls_shallow(self, tree: Tree) -> list[STCall]:
        """Find calls in the condition/expression parts, not in nested stmts."""
        calls: list[STCall] = []
        for child in tree.children:
            if isinstance(child, Tree):
                if child.data == "call_expr":
                    calls.append(self._extract_call(child))
                elif child.data not in _STMT_TYPES + (
                    "elsif_clause", "else_clause", "case_labels",
                ):
                    self._walk_for_calls(child, calls)
        return calls

    def _walk_for_calls(self, tree: Tree, calls: list[STCall]) -> None:
        if not isinstance(tree, Tree):
            return
        if tree.data == "call_expr":
            calls.append(self._extract_call(tree))
            return
        for child in tree.children:
            if isinstance(child, Tree):
                self._walk_for_calls(child, calls)


def _reconstruct_expr(node) -> str:
    """Reconstruct expression text from a parse tree node."""
    if isinstance(node, Token):
        return str(node)
    if isinstance(node, Tree):
        parts: list[str] = []
        for child in node.children:
            parts.append(_reconstruct_expr(child))
        if node.data == "bin_op":
            if len(parts) >= 3:
                return f"{parts[0]} {parts[1]} {parts[2]}"
            return " ".join(parts)
        if node.data == "unary_op":
            return " ".join(parts)
        if node.data == "member_access":
            # MEMBER_ACCESS token includes the dot
            return "".join(parts)
        if node.data == "bit_access":
            return "".join(parts)
        if node.data == "index_access":
            # postfix_expr [ expr_list ]
            base = parts[0] if parts else ""
            indices = ", ".join(parts[1:]) if len(parts) > 1 else ""
            return f"{base}[{indices}]"
        if node.data == "dyn_bit_access":
            # children: postfix_expr, DYN_BIT_START token (".["), expr
            base = parts[0] if parts else ""
            idx = parts[2] if len(parts) > 2 else ""
            return f"{base}.[{idx}]"
        if node.data == "paren_expr":
            inner = parts[0] if parts else ""
            return f"({inner})"
        if node.data == "call_expr":
            name = parts[0] if parts else ""
            # Simplified reconstruction
            return f"{name}(...)"
        if node.data == "cross_ref":
            return "".join(parts)
        if node.data == "expr_list":
            return ", ".join(parts)
        if node.data in ("call_arg_expr", "call_args"):
            return ", ".join(parts)
        return "".join(parts)
    return str(node)


def _try_compute_iteration_bound(
    start_text: str | None,
    end_text: str | None,
    step_text: str | None,
) -> int | None:
    """Try to compute the max iteration count for a FOR loop from literal bounds.

    Returns None if any bound is non-literal (variable, expression with variables).
    """
    if start_text is None or end_text is None:
        return None
    try:
        start_val = int(start_text)
        end_val = int(end_text)
        step_val = int(step_text) if step_text else 1
        if step_val == 0:
            return None  # infinite loop
        if step_val > 0:
            if end_val < start_val:
                return 0
            return ((end_val - start_val) // step_val) + 1
        else:
            if start_val < end_val:
                return 0
            return ((start_val - end_val) // abs(step_val)) + 1
    except (ValueError, TypeError):
        return None


def _has_exit_statement(children: list) -> bool:
    """Recursively check if any child statement is an EXIT."""
    for stmt in children:
        if stmt.kind == "exit":
            return True
        if stmt.children and _has_exit_statement(stmt.children):
            return True
    return False


class STParser:
    """Reusable ST routine text parser.

    Loads the grammar once at construction and reuses it for every
    ``parse()`` call.  Thread-safe for concurrent reads once constructed.
    """

    def __init__(self) -> None:
        grammar_text = _GRAMMAR_PATH.read_text(encoding="utf-8")
        self._lark = Lark(grammar_text, parser="lalr")
        self._visitor = _STTreeVisitor()

    def parse(self, text: str) -> ParsedST:
        """Parse ST source text and return a ``ParsedST``.

        Returns an empty ParsedST for None/empty/whitespace-only input.
        Raises ``STParseError`` if the text cannot be parsed.
        """
        if not text or not text.strip():
            return ParsedST()

        try:
            tree = self._lark.parse(text)
        except LarkError as exc:
            raise STParseError(text, exc) from exc

        statements = self._visitor.visit_start(tree)
        return ParsedST(statements=statements)

    def parse_lines(self, lines: list[str]) -> ParsedST:
        """Parse a list of ST lines (as found in L5X STContent).

        Joins lines and parses as a single block.
        """
        combined = "\n".join(lines)
        return self.parse(combined)


class STParseError(Exception):
    """Raised when ST text cannot be parsed."""

    def __init__(self, text: str, cause: Exception) -> None:
        self.text = text
        self.cause = cause
        preview = text[:120] + ("..." if len(text) > 120 else "")
        super().__init__(f"Failed to parse ST: {preview!r}\n  Cause: {cause}")
