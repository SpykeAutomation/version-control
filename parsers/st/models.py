"""
AST models for parsed Structured Text (ST) routine content.

The tree mirrors the ST structure:
  ParsedST
    ├── STStatement     (if, for, while, case, assign, call, expr)
    └── STCall          (function/instruction call with arguments)

Helper methods on ParsedST flatten the tree for common checker queries
like "find all calls to GSV in this routine."
"""
from __future__ import annotations

from typing import Optional, Union

from pydantic import BaseModel


class STCall(BaseModel):
    """A function or instruction call: NAME(args).

    Each argument is either a string (reconstructed expression text)
    or None for empty arguments (e.g. GSV(Class,,Attr,Dest)).
    """

    name: str
    args: list[Optional[str]] = []


class STAssignment(BaseModel):
    """An assignment statement: lvalue := rvalue."""

    target: str
    value: str


class STStatement(BaseModel):
    """A generic statement node.

    kind indicates the statement type: 'if', 'for', 'while', 'repeat',
    'case', 'assign', 'call', 'expr', 'exit', 'return'.
    """

    kind: str
    # Condition expression text (for if/elsif/while/repeat)
    condition: Optional[str] = None
    # For call statements, the call details
    call: Optional[STCall] = None
    # For assignment statements
    assignment: Optional[STAssignment] = None
    # Child statements (body of if/for/while/etc.)
    children: list[STStatement] = []
    # Calls found anywhere within this statement and its children
    nested_calls: list[STCall] = []
    # Loop metadata (populated for for/while/repeat statements)
    loop_header: Optional[str] = None       # e.g. "FOR i := 0 TO arrayLen BY 1"
    loop_var: Optional[str] = None          # FOR loop iterator variable
    loop_start: Optional[str] = None        # FOR loop start expression
    loop_end: Optional[str] = None          # FOR loop end expression
    loop_step: Optional[str] = None         # FOR loop step (None = default 1)
    iteration_bound: Optional[int] = None   # Static max iterations (FOR only)
    has_exit: bool = False                  # True if body contains EXIT


class ParsedST(BaseModel):
    """The full AST for one parsed ST routine (all lines combined)."""

    statements: list[STStatement] = []

    def all_calls(self) -> list[STCall]:
        """Return every function/instruction call in the routine, flattened."""
        result: list[STCall] = []
        _collect_calls(self.statements, result)
        return result

    def has_call(self, name: str) -> bool:
        """Check whether a call with the given name exists (case-insensitive)."""
        name_upper = name.upper()
        return any(c.name.upper() == name_upper for c in self.all_calls())

    def find_calls(self, name: str) -> list[STCall]:
        """Return all calls matching the given name (case-insensitive)."""
        name_upper = name.upper()
        return [c for c in self.all_calls() if c.name.upper() == name_upper]

    def all_assignments(self) -> list[STAssignment]:
        """Return every assignment in the routine, flattened."""
        result: list[STAssignment] = []
        _collect_assignments(self.statements, result)
        return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _collect_calls(stmts: list[STStatement], out: list[STCall]) -> None:
    for stmt in stmts:
        if stmt.call is not None:
            out.append(stmt.call)
        out.extend(stmt.nested_calls)
        _collect_calls(stmt.children, out)


def _collect_assignments(stmts: list[STStatement], out: list[STAssignment]) -> None:
    for stmt in stmts:
        if stmt.assignment is not None:
            out.append(stmt.assignment)
        _collect_assignments(stmt.children, out)
