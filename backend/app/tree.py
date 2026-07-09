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
# changes in a way a renderer must notice. v2: include I/O modules whose parent
# is a self-reference or missing (previously dropped, so the I/O folder was
# absent). v3: Studio 5000 organizer categories — Data Types subfolders
# (User-Defined / Strings / Add-On-Defined), AOI routine children, Motion
# Groups, Power-Up / Controller Fault Handler folders, and task program
# references now carrying the program's routine subtree.
SCHEMA_VERSION = 3

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


def _routine_nodes(
    prog, pc: Optional[ProgramChange], ctrl_name: str, key_prefix: str
) -> list[TreeNode]:
    """Routine nodes for one program, with ladder identity set and removed
    routines injected from its ProgramChange. `key_prefix` namespaces the keys
    (e.g. "program:P" or "task:T/program:P") so the same program can appear
    both in the flat Programs folder and under the task that schedules it."""
    rc_by_name = {r.name: r for r in (pc.routines if pc else [])}
    prog_added = pc is not None and pc.kind == "added"
    nodes: list[TreeNode] = []
    for rt in prog.routines:
        rc = rc_by_name.get(rt.name)
        status: Status = rc.kind if rc else ("added" if prog_added else "unchanged")
        nodes.append(
            TreeNode(
                key=f"{key_prefix}/routine:{rt.name}",
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
            nodes.append(
                TreeNode(
                    key=f"{key_prefix}/routine:{rc.name}",
                    label=rc.name,
                    kind="routine",
                    status="removed",
                    routine_type=rc.routine_type,
                    controller=ctrl_name,
                    program=prog.name,
                    routine=rc.name,
                )
            )
    return nodes


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

    # --- Tasks: each task lists the programs it schedules, each carrying the
    # program's full routine subtree (namespaced keys, so they stay unique
    # against the flat Programs folder, which the frontend still relies on).
    progs_by_name = {p.name: p for p in doc.programs}
    task_nodes: list[TreeNode] = []
    for task in doc.tasks:
        refs = []
        for pname in task.scheduled_programs:
            prog = progs_by_name.get(pname)
            refs.append(
                TreeNode(
                    key=f"task:{task.name}/program:{pname}",
                    label=pname,
                    kind="program",
                    status=_program_status(prog_changes.get(pname)),
                    program=pname,
                    children=_routine_nodes(
                        prog,
                        prog_changes.get(pname),
                        ctrl_name,
                        f"task:{task.name}/program:{pname}",
                    )
                    if prog is not None  # a partial export can schedule an absent program
                    else [],
                )
            )
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

    # --- Motion Groups: MOTION_GROUP tags with their axes nested beneath.
    motion_nodes = _motion_nodes(doc, tag_status)
    if motion_nodes:
        folders.append(
            TreeNode(
                key="folder:motion", label="Motion Groups", kind="folder",
                children=motion_nodes,
            )
        )

    # --- Handler folders: a program *reference* (like a task's), shown only
    # when the controller names one.
    for handler, key, label in (
        (doc.controller.power_loss_program, "folder:powerup-handler", "Power-Up Handler"),
        (doc.controller.fault_handler_program, "folder:fault-handler", "Controller Fault Handler"),
    ):
        if handler:
            folders.append(
                TreeNode(
                    key=key,
                    label=label,
                    kind="folder",
                    children=[
                        TreeNode(
                            key=f"{key}/program:{handler}",
                            label=handler,
                            kind="program",
                            status=_program_status(prog_changes.get(handler)),
                            program=handler,
                        )
                    ],
                )
            )

    # --- Programs (flat) -> Routines. Routine nodes carry ladder identity.
    prog_nodes: list[TreeNode] = []
    for prog in doc.programs:
        pc = prog_changes.get(prog.name)
        prog_nodes.append(
            TreeNode(
                key=f"program:{prog.name}",
                label=prog.name,
                kind="program",
                status=_program_status(pc),
                program=prog.name,
                children=_routine_nodes(prog, pc, ctrl_name, f"program:{prog.name}"),
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

    # --- Add-On Instructions: each AOI with its routines as children. AOI
    # routine nodes carry NO ladder identity (controller/program/routine stay
    # None) — they map to no ladder-diff card; renderers key off the prefix.
    aoi_nodes: list[TreeNode] = []
    for aoi in doc.add_on_instructions:
        st = aoi_status.get(aoi.name, "unchanged")
        aoi_nodes.append(
            TreeNode(
                key=f"aoi:{aoi.name}",
                label=aoi.name,
                kind="aoi",
                status=st,
                children=[
                    TreeNode(
                        key=f"aoi:{aoi.name}/routine:{rt.name}",
                        label=rt.name,
                        kind="routine",
                        routine_type=rt.type,
                        # The ChangeSet tracks an AOI as one entity, so routines
                        # only inherit a whole-AOI add; edits badge the AOI node.
                        status="added" if st == "added" else "unchanged",
                    )
                    for rt in aoi.routines
                ],
            )
        )
    head_aoi_names = {a.name for a in doc.add_on_instructions}
    for name, st in aoi_status.items():
        if st == "removed" and name not in head_aoi_names:
            aoi_nodes.append(
                TreeNode(key=f"aoi:{name}", label=name, kind="aoi", status="removed")
            )
    if aoi_nodes:
        folders.append(
            TreeNode(
                key="folder:aois", label="Add-On Instructions", kind="folder",
                children=aoi_nodes,
            )
        )

    # --- Data Types, split into Studio 5000's subfolders.
    folders.extend(_datatype_folder(doc, dt_status, aoi_status))

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


def _datatype_folder(
    doc: L5XDocument, dt_status: dict[str, str], aoi_status: dict[str, str]
) -> list[TreeNode]:
    """The Data Types folder, split into Studio 5000's subfolders — each shown
    only when non-empty: "User-Defined", "Strings" (family == "StringFamily"),
    and "Add-On-Defined" (one reference leaf per AOI, since every AOI defines a
    data type). Predefined / Module-Defined types are not present in an L5X
    export, so those subfolders are omitted. A removed type's family is unknown
    at head, so removed types list under User-Defined."""
    user: list[str] = []
    strings: list[str] = []
    for d in doc.data_types:
        (strings if d.family == "StringFamily" else user).append(d.name)
    head = {d.name for d in doc.data_types}
    user += [n for n, s in dt_status.items() if s == "removed" and n not in head]

    def leaves(names: list[str], key_fmt: str, status: dict[str, str]) -> list[TreeNode]:
        return [
            TreeNode(
                key=key_fmt.format(name=n), label=n, kind="datatype",
                status=status.get(n, "unchanged"),
            )
            for n in names
        ]

    aoi_names = [a.name for a in doc.add_on_instructions]
    aoi_names += [
        n for n, s in aoi_status.items()
        if s == "removed" and n not in set(aoi_names)
    ]

    subfolders: list[TreeNode] = []
    if user:
        subfolders.append(
            TreeNode(
                key="folder:datatypes/user-defined", label="User-Defined",
                kind="folder", children=leaves(user, "datatype:{name}", dt_status),
            )
        )
    if strings:
        subfolders.append(
            TreeNode(
                key="folder:datatypes/strings", label="Strings",
                kind="folder", children=leaves(strings, "datatype:{name}", dt_status),
            )
        )
    if aoi_names:
        subfolders.append(
            TreeNode(
                key="folder:datatypes/add-on-defined", label="Add-On-Defined",
                kind="folder", children=leaves(aoi_names, "datatype:aoi:{name}", aoi_status),
            )
        )
    if not subfolders:
        return []
    return [
        TreeNode(key="folder:datatypes", label="Data Types", kind="folder", children=subfolders)
    ]


def _motion_nodes(doc: L5XDocument, tag_status: dict[str, str]) -> list[TreeNode]:
    """Motion Groups content: each MOTION_GROUP tag as a group node with its
    AXIS_* tags nested by the axis's MotionGroup reference. An axis whose group
    is missing/absent still renders, flat; a group with no axes is childless.
    These are tags, so they ALSO stay listed under Controller Tags (no
    de-duplication). Empty when the project has no groups and no axes."""
    groups = [t for t in doc.controller_tags if t.data_type == "MOTION_GROUP"]
    axes = [t for t in doc.controller_tags if t.data_type.startswith("AXIS")]
    if not groups and not axes:
        return []
    group_names = {g.name for g in groups}
    by_group: dict[Optional[str], list] = {}
    for ax in axes:
        ref = ax.motion_config.get("MotionGroup")
        by_group.setdefault(ref if ref in group_names else None, []).append(ax)

    def axis_node(ax, group_ref: str) -> TreeNode:
        return TreeNode(
            key=f"motion:{group_ref}/axis:{ax.name}", label=ax.name, kind="tag",
            status=tag_status.get(ax.name, "unchanged"),
        )

    nodes = [
        TreeNode(
            key=f"motion:{g.name}", label=g.name, kind="tag",
            status=tag_status.get(g.name, "unchanged"),
            children=[axis_node(ax, g.name) for ax in by_group.get(g.name, [])],
        )
        for g in groups
    ]
    # Orphan axes keep their (missing) group reference in the key so keys stay
    # unique and the broken reference stays visible.
    nodes += [
        axis_node(ax, ax.motion_config.get("MotionGroup") or "")
        for ax in by_group.get(None, [])
    ]
    return nodes


def _module_nodes(doc: L5XDocument, status: dict[str, str]) -> list[TreeNode]:
    """Build the I/O module nodes, nested by parent_module into a rack tree."""
    names = {m.name for m in doc.modules}
    # Group children under their parent. The local chassis module names itself
    # as its parent, and a partial export can point at a parent that isn't in
    # the file — both are rack roots, so normalise them to "no parent" (None).
    # Without this the root would be its own child and never appear (and the
    # recursion would loop).
    by_parent: dict[Optional[str], list] = {}
    for m in doc.modules:
        parent = m.parent_module
        if parent == m.name or parent not in names:
            parent = None
        by_parent.setdefault(parent, []).append(m)

    def build(m, seen: set[str]) -> Optional[TreeNode]:
        if m.name in seen:  # defensive: never recurse through a cycle
            return None
        seen = seen | {m.name}
        children = [
            node for c in by_parent.get(m.name, []) if (node := build(c, seen)) is not None
        ]
        return TreeNode(
            key=f"module:{m.name}",
            label=m.name,
            kind="module",
            status=status.get(m.name, "unchanged"),
            children=children,
        )

    nodes = [n for m in by_parent.get(None, []) if (n := build(m, set())) is not None]
    for name, st in status.items():
        if st == "removed" and name not in names:
            nodes.append(
                TreeNode(key=f"module:{name}", label=name, kind="module", status="removed")
            )
    return nodes
