"""
Models for the result of comparing two PLC projects.

A diff produces a ChangeSet: structured lists of what was added, removed,
and changed in each part of the project. Tools consume the ChangeSet as
data (it dumps to JSON); the plain-text view in render.py is just one way
to look at it.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel


class FieldChange(BaseModel):
    """One value that differs, with a dotted path saying where.

    Examples: "description", "values.Cmd.Timer.PRE", "members[Pt1].data_type".
    A missing side is None (the field was added or removed).
    """

    path: str
    old: Any = None
    new: Any = None


class RungChange(BaseModel):
    """One ladder rung that was added, removed, or changed.

    Rungs are matched by content, so a rung that only got renumbered is not
    a change. "comment_changed" means the logic is identical and only the
    attached comment text differs.
    """

    kind: Literal["added", "removed", "modified", "comment_changed"]
    old_number: Optional[int] = None
    new_number: Optional[int] = None
    old_text: Optional[str] = None
    new_text: Optional[str] = None
    old_comment: Optional[str] = None
    new_comment: Optional[str] = None


class LineChange(BaseModel):
    """One structured-text line that was added, removed, or changed."""

    kind: Literal["added", "removed", "modified"]
    old_number: Optional[int] = None
    new_number: Optional[int] = None
    old_text: Optional[str] = None
    new_text: Optional[str] = None


class EntityChange(BaseModel):
    """A named thing (module, tag, UDT, AOI, task) that changed."""

    name: str
    kind: Literal["added", "removed", "modified"]
    fields: list[FieldChange] = []  # empty for added/removed


class RoutineChange(BaseModel):
    name: str
    kind: Literal["added", "removed", "modified"]
    routine_type: Optional[str] = None  # RLL, ST, FBD, SFC
    fields: list[FieldChange] = []
    rungs: list[RungChange] = []  # ladder routines
    lines: list[LineChange] = []  # structured-text routines
    # The text changed but it parses to the same logic (spacing, case).
    formatting_only: bool = False
    # Anything the diff cannot break down further, e.g. FBD/SFC content.
    note: Optional[str] = None


class ProgramChange(BaseModel):
    name: str
    kind: Literal["added", "removed", "modified"]
    fields: list[FieldChange] = []  # the program's own settings
    tags: list[EntityChange] = []
    routines: list[RoutineChange] = []


class ChangeSet(BaseModel):
    """Everything that differs between two versions of a project."""

    controller: list[FieldChange] = []  # paths prefixed metadata. / controller.
    modules: list[EntityChange] = []
    data_types: list[EntityChange] = []
    add_on_instructions: list[EntityChange] = []
    controller_tags: list[EntityChange] = []
    programs: list[ProgramChange] = []
    tasks: list[EntityChange] = []

    def is_empty(self) -> bool:
        """True when the two versions have no differences."""
        return not (
            self.controller
            or self.modules
            or self.data_types
            or self.add_on_instructions
            or self.controller_tags
            or self.programs
            or self.tasks
        )
