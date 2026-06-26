"""Build a project-organizer tree for a commit, with change status overlaid.

The single-commit page shows a ladder diff but nothing about *where* a change
sits in the program. This module produces that map: the full Studio 5000
Controller Organizer (Controller -> Tasks / Programs / Routines, plus Add-On
Instructions, Data Types, Controller Tags, I/O) read from the snapshot at the
commit, with each node tagged added / removed / modified / unchanged by
overlaying the commit's ChangeSet onto the structure.

The tree is the structure (every node, changed or not); the ChangeSet only
says what differs. Routine nodes carry (controller, program, routine) verbatim
so a renderer can match a node to its ladder-diff card.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

from diff.models import ChangeSet, ProgramChange
from parsers.l5x.models import L5XDocument

# Bump alongside the cache view in diff_cache.SCHEMA_VERSION when this shape
# changes in a way a renderer must notice.
SCHEMA_VERSION = 1

NodeKind = Literal[
    "controller", "folder", "program", "routine", "aoi", "datatype", "tag", "module", "task"
]
Status = Literal["unchanged", "added", "removed", "modified"]


class TreeNode(BaseModel):
    """One node in the organizer tree.

    `status` is the node's own change; `descendant_changed` rolls up whether
    anything beneath it changed (so a folder can be auto-opened and flagged
    without itself being changed). `controller`/`program`/`routine` are set
    only on routine nodes and map the node to its ladder-diff card.
    """

    key: str
    label: str
    kind: NodeKind
    status: Status = "unchanged"
    descendant_changed: bool = False
    routine_type: Optional[str] = None
    controller: Optional[str] = None
    program: Optional[str] = None
    routine: Optional[str] = None
    children: list["TreeNode"] = []


# `children` is a list of TreeNode from inside TreeNode, so resolve the forward
# ref once the class exists (mirrors diff.ladder_models.Element).
TreeNode.model_rebuild()


class ProjectTree(BaseModel):
    """The organizer tree for one file at one commit."""

    schema_version: int = SCHEMA_VERSION
    root: TreeNode


def _entity_status(changes: list) -> dict[str, str]:
    """Map a ChangeSet entity list (modules, tags, ...) to {name: kind}."""
    return {c.name: c.kind for c in changes}


def _program_status(pc: Optional[ProgramChange]) -> Status:
    """Status to show on a program node itself.

    A program reads as added/removed when the whole program is. For a
    "modified" program we only badge the node when its *own* settings or tags
    changed; routine changes light up the routine nodes and roll up to the
    folder, so the program isn't double-flagged for a change that really lives
    one level down.
    """
    if pc is None:
        return "unchanged"
    if pc.kind in ("added", "removed"):
        return pc.kind
    return "modified" if (pc.fields or pc.tags) else "unchanged"


def _finalize(node: TreeNode) -> None:
    """Set descendant_changed bottom-up for the whole subtree."""
    changed = False
    for child in node.children:
        _finalize(child)
        if child.status != "unchanged" or child.descendant_changed:
            changed = True
    node.descendant_changed = changed


def build_project_tree(doc: L5XDocument, changes: ChangeSet) -> ProjectTree:
    """Build the organizer tree for `doc`, tagged with `changes`.

    `doc` is the snapshot at the head commit (the full structure); `changes`
    is the diff against the base. Removed entities are absent from `doc`, so
    they are injected from `changes` and badged "removed".
    """
    ctrl_name = doc.controller.name
    prog_changes = {p.name: p for p in changes.programs}
    mod_status = _entity_status(changes.modules)
    dt_status = _entity_status(changes.data_types)
    aoi_status = _entity_status(changes.add_on_instructions)
    tag_status = _entity_status(changes.controller_tags)
    task_status = _entity_status(changes.tasks)

    folders: list[TreeNode] = []

    # --- Tasks: each task lists the programs it schedules (a reference, not a
    # second copy of the routine tree — the Programs folder owns those).
    task_nodes: list[TreeNode] = []
    for task in doc.tasks:
        refs = [
            TreeNode(
                key=f"task:{task.name}/program:{pname}",
                label=pname,
                kind="program",
                status=_program_status(prog_changes.get(pname)),
                program=pname,
            )
            for pname in task.scheduled_programs
        ]
        task_nodes.append(
            TreeNode(
                key=f"task:{task.name}",
                label=task.name,
                kind="task",
                status=task_status.get(task.name, "unchanged"),
                children=refs,
            )
        )
    head_task_names = {t.name for t in doc.tasks}
    for name, kind in task_status.items():
        if kind == "removed" and name not in head_task_names:
            task_nodes.append(
                TreeNode(key=f"task:{name}", label=name, kind="task", status="removed")
            )
    if task_nodes:
        folders.append(
            TreeNode(key="folder:tasks", label="Tasks", kind="folder", children=task_nodes)
        )

    # --- Programs (flat) -> Routines. Routine nodes carry ladder identity.
    prog_nodes: list[TreeNode] = []
    for prog in doc.programs:
        pc = prog_changes.get(prog.name)
        rc_by_name = {r.name: r for r in (pc.routines if pc else [])}
        prog_added = pc is not None and pc.kind == "added"
        rout_nodes: list[TreeNode] = []
        for rt in prog.routines:
            rc = rc_by_name.get(rt.name)
            status: Status = rc.kind if rc else ("added" if prog_added else "unchanged")
            rout_nodes.append(
                TreeNode(
                    key=f"program:{prog.name}/routine:{rt.name}",
                    label=rt.name,
                    kind="routine",
                    status=status,
                    routine_type=rt.type,
                    controller=ctrl_name,
                    program=prog.name,
                    routine=rt.name,
                )
            )
        head_rt_names = {rt.name for rt in prog.routines}
        for rc in pc.routines if pc else []:
            if rc.kind == "removed" and rc.name not in head_rt_names:
                rout_nodes.append(
                    TreeNode(
                        key=f"program:{prog.name}/routine:{rc.name}",
                        label=rc.name,
                        kind="routine",
                        status="removed",
                        routine_type=rc.routine_type,
                        controller=ctrl_name,
                        program=prog.name,
                        routine=rc.name,
                    )
                )
        prog_nodes.append(
            TreeNode(
                key=f"program:{prog.name}",
                label=prog.name,
                kind="program",
                status=_program_status(pc),
                program=prog.name,
                children=rout_nodes,
            )
        )
    head_prog_names = {p.name for p in doc.programs}
    for pc in changes.programs:
        if pc.kind == "removed" and pc.name not in head_prog_names:
            rout_nodes = [
                TreeNode(
                    key=f"program:{pc.name}/routine:{rc.name}",
                    label=rc.name,
                    kind="routine",
                    status="removed",
                    routine_type=rc.routine_type,
                    controller=ctrl_name,
                    program=pc.name,
                    routine=rc.name,
                )
                for rc in pc.routines
            ]
            prog_nodes.append(
                TreeNode(
                    key=f"program:{pc.name}",
                    label=pc.name,
                    kind="program",
                    status="removed",
                    program=pc.name,
                    children=rout_nodes,
                )
            )
    if prog_nodes:
        folders.append(
            TreeNode(
                key="folder:programs", label="Programs", kind="folder", children=prog_nodes
            )
        )

    # --- Add-On Instructions (leaves; AOI routines have no ladder card).
    folders.extend(
        _entity_folder(
            "folder:aois",
            "Add-On Instructions",
            "aoi",
            [a.name for a in doc.add_on_instructions],
            aoi_status,
        )
    )

    # --- Data Types.
    folders.extend(
        _entity_folder(
            "folder:datatypes",
            "Data Types",
            "datatype",
            [d.name for d in doc.data_types],
            dt_status,
        )
    )

    # --- Controller Tags.
    folders.extend(
        _entity_folder(
            "folder:tags",
            "Controller Tags",
            "tag",
            [t.name for t in doc.controller_tags],
            tag_status,
        )
    )

    # --- I/O Configuration: modules nested by parent to form the rack tree.
    io_nodes = _module_nodes(doc, mod_status)
    if io_nodes:
        folders.append(
            TreeNode(
                key="folder:io", label="I/O Configuration", kind="folder", children=io_nodes
            )
        )

    root = TreeNode(
        key="controller",
        label=ctrl_name,
        kind="controller",
        status="modified" if changes.controller else "unchanged",
        children=folders,
    )
    _finalize(root)
    return ProjectTree(root=root)


def _entity_folder(
    key: str, label: str, kind: NodeKind, head_names: list[str], status: dict[str, str]
) -> list[TreeNode]:
    """Build a flat folder of leaf entities; return [] when it would be empty.

    Removed entities are absent from `head_names`, so they are appended from
    the status map.
    """
    nodes = [
        TreeNode(
            key=f"{kind}:{name}", label=name, kind=kind, status=status.get(name, "unchanged")
        )
        for name in head_names
    ]
    head = set(head_names)
    for name, st in status.items():
        if st == "removed" and name not in head:
            nodes.append(TreeNode(key=f"{kind}:{name}", label=name, kind=kind, status="removed"))
    if not nodes:
        return []
    return [TreeNode(key=key, label=label, kind="folder", children=nodes)]


def _module_nodes(doc: L5XDocument, status: dict[str, str]) -> list[TreeNode]:
    """Build the I/O module nodes, nested by parent_module into a rack tree."""
    names = {m.name for m in doc.modules}
    by_parent: dict[Optional[str], list] = {}
    for m in doc.modules:
        by_parent.setdefault(m.parent_module, []).append(m)

    def build(m) -> TreeNode:
        return TreeNode(
            key=f"module:{m.name}",
            label=m.name,
            kind="module",
            status=status.get(m.name, "unchanged"),
            children=[build(c) for c in by_parent.get(m.name, [])],
        )

    # A module is a root when it has no parent, or its parent isn't in the file
    # (a partial export) — otherwise it would be orphaned out of the tree.
    roots = [m for m in doc.modules if not m.parent_module or m.parent_module not in names]
    nodes = [build(m) for m in roots]
    for name, st in status.items():
        if st == "removed" and name not in names:
            nodes.append(
                TreeNode(key=f"module:{name}", label=name, kind="module", status="removed")
            )
    return nodes
