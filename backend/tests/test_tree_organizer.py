"""Organizer-tree structure (schema v4): programs live under their scheduling
home like in Studio 5000 — tasks own their scheduled programs' full subtrees
in schedule order, handler folders own theirs, everything else sits in
"Unscheduled Programs" under Tasks, and there is no flat Programs folder.
Plus the v3 categories: Data Types subfolders, AOI routine children, Motion
Groups."""
import pytest

from app.tree import SCHEMA_VERSION, TreeNode, build_project_tree
from diff import diff_documents
from diff.models import ChangeSet
from fixtures_l5x import make_l5x

# One document exercising every organizer category: a UDT and a string type,
# an AOI with a routine, a motion group with one grouped and one orphan axis,
# both controller handler programs, two tasks (one scheduling three programs
# in deliberately non-alphabetical order), and an unscheduled program.
ORGANIZER = make_l5x(
    controller_attrs='PowerLossProgram="PowerUp" MajorFaultProgram="FaultProg"',
    body=(
        "<DataTypes>"
        '<DataType Name="DemoUDT" Family="NoFamily" Class="User">'
        '<Members><Member Name="A" DataType="DINT" Dimension="0"/></Members>'
        "</DataType>"
        '<DataType Name="MyString" Family="StringFamily" Class="User">'
        '<Members><Member Name="LEN" DataType="DINT" Dimension="0"/>'
        '<Member Name="DATA" DataType="SINT" Dimension="24" Radix="ASCII"/></Members>'
        "</DataType>"
        "</DataTypes>"
        "<AddOnInstructionDefinitions>"
        '<AddOnInstructionDefinition Name="ValveCtl" Revision="1.0">'
        "<Parameters/>"
        '<Routines><Routine Name="Logic" Type="RLL">'
        '<RLLContent><Rung Number="0"><Text>NOP();</Text></Rung></RLLContent>'
        "</Routine></Routines>"
        "</AddOnInstructionDefinition>"
        "</AddOnInstructionDefinitions>"
        "<Tags>"
        '<Tag Name="MG1" TagType="Base" DataType="MOTION_GROUP">'
        '<Data Format="MotionGroup"><MotionGroupParameters GroupType="Standard"/></Data>'
        "</Tag>"
        '<Tag Name="AxisA" TagType="Base" DataType="AXIS_CIP_DRIVE">'
        '<Data Format="Axis"><Params MotionGroup="MG1" CtrlMode="Position"/></Data>'
        "</Tag>"
        '<Tag Name="AxisOrphan" TagType="Base" DataType="AXIS_VIRTUAL">'
        '<Data Format="Axis"><Params MotionGroup="GhostGroup"/></Data>'
        "</Tag>"
        '<Tag Name="PlainTag" TagType="Base" DataType="DINT"/>'
        "</Tags>"
        "<Programs>"
        '<Program Name="MixerProg" MainRoutineName="Main">'
        '<Routines><Routine Name="Main" Type="RLL">'
        '<RLLContent><Rung Number="0"><Text>XIC(PlainTag)OTE(PlainTag);</Text></Rung>'
        "</RLLContent></Routine></Routines>"
        "</Program>"
        '<Program Name="Zeta">'
        '<Routines><Routine Name="ZMain" Type="RLL"><RLLContent/></Routine></Routines>'
        "</Program>"
        '<Program Name="Alpha">'
        '<Routines><Routine Name="AMain" Type="RLL"><RLLContent/></Routine></Routines>'
        "</Program>"
        '<Program Name="SideProg">'
        '<Routines><Routine Name="SMain" Type="RLL"><RLLContent/></Routine></Routines>'
        "</Program>"
        '<Program Name="Lonely">'
        '<Routines><Routine Name="LMain" Type="RLL"><RLLContent/></Routine></Routines>'
        "</Program>"
        '<Program Name="PowerUp">'
        '<Routines><Routine Name="Boot" Type="RLL"><RLLContent/></Routine></Routines>'
        "</Program>"
        '<Program Name="FaultProg"><Routines/></Program>'
        "</Programs>"
        "<Tasks>"
        '<Task Name="MainTask" Type="CONTINUOUS">'
        "<ScheduledPrograms>"
        '<ScheduledProgram Name="MixerProg"/>'
        '<ScheduledProgram Name="Zeta"/>'
        '<ScheduledProgram Name="Alpha"/>'
        "</ScheduledPrograms>"
        "</Task>"
        '<Task Name="SideTask" Type="PERIODIC" Rate="10">'
        '<ScheduledPrograms><ScheduledProgram Name="SideProg"/></ScheduledPrograms>'
        "</Task>"
        "</Tasks>"
    ),
)

# The same document with the one rung edited — for status-overlay tests.
ORGANIZER_EDIT = ORGANIZER.replace(
    "XIC(PlainTag)OTE(PlainTag);", "XIC(PlainTag)XIC(PlainTag)OTE(PlainTag);"
)

# Zeta deleted outright: the program and its schedule entry both gone.
ORGANIZER_NO_ZETA = ORGANIZER.replace(
    '<Program Name="Zeta">'
    '<Routines><Routine Name="ZMain" Type="RLL"><RLLContent/></Routine></Routines>'
    "</Program>",
    "",
).replace('<ScheduledProgram Name="Zeta"/>', "")

# SideTask deleted along with the one program it scheduled.
ORGANIZER_NO_SIDETASK = ORGANIZER.replace(
    '<Program Name="SideProg">'
    '<Routines><Routine Name="SMain" Type="RLL"><RLLContent/></Routine></Routines>'
    "</Program>",
    "",
).replace(
    '<Task Name="SideTask" Type="PERIODIC" Rate="10">'
    '<ScheduledPrograms><ScheduledProgram Name="SideProg"/></ScheduledPrograms>'
    "</Task>",
    "",
)


def find(node: TreeNode, key: str) -> TreeNode | None:
    """Depth-first search of the tree for the node with `key`."""
    if node.key == key:
        return node
    for child in node.children:
        if (hit := find(child, key)) is not None:
            return hit
    return None


def program_names(node: TreeNode) -> list[str]:
    """Every kind=="program" node's program identity, in tree order."""
    names = [node.program] if node.kind == "program" else []
    for child in node.children:
        names += program_names(child)
    return names


@pytest.fixture(scope="module")
def root(l5x) -> TreeNode:
    return build_project_tree(l5x.parse_string(ORGANIZER), ChangeSet()).root


@pytest.fixture(scope="module")
def empty_root(l5x) -> TreeNode:
    """A document with no motion tags and no handler attributes."""
    return build_project_tree(l5x.parse_string(make_l5x()), ChangeSet()).root


def test_schema_version_bumped(l5x):
    assert SCHEMA_VERSION == 4
    tree = build_project_tree(l5x.parse_string(ORGANIZER), ChangeSet())
    assert tree.schema_version == 4


def test_no_programs_folder_and_every_program_exactly_once(root, l5x):
    assert find(root, "folder:programs") is None
    doc = l5x.parse_string(ORGANIZER)
    names = program_names(root)
    assert len(names) == len(set(names)), "a program appears twice"
    assert sorted(names) == sorted(p.name for p in doc.programs), "a program was lost"


def test_scheduled_programs_sit_under_their_task_in_schedule_order(root):
    task = find(root, "task:MainTask")
    assert task is not None and task.kind == "task"
    # ScheduledPrograms order is execution order — never sorted alphabetically.
    assert [c.key for c in task.children] == [
        "task:MainTask/program:MixerProg",
        "task:MainTask/program:Zeta",
        "task:MainTask/program:Alpha",
    ]
    assert all(c.kind == "program" for c in task.children)
    # Full subtrees: routines are present, with ladder-card identity.
    rt = find(task, "task:MainTask/program:MixerProg/routine:Main")
    assert rt is not None and rt.kind == "routine" and rt.routine_type == "RLL"
    assert rt.controller == "ctrllr" and rt.program == "MixerProg" and rt.routine == "Main"
    side = find(root, "task:SideTask")
    assert [c.key for c in side.children] == ["task:SideTask/program:SideProg"]


def test_handler_programs_own_full_subtrees(root, empty_root):
    powerup = find(root, "folder:powerup-handler")
    assert powerup is not None and powerup.label == "Power-Up Handler"
    prog = powerup.children[0]
    assert prog.key == "folder:powerup-handler/program:PowerUp"
    assert prog.kind == "program" and prog.program == "PowerUp"
    rt = find(prog, "folder:powerup-handler/program:PowerUp/routine:Boot")
    assert rt is not None and rt.controller == "ctrllr" and rt.program == "PowerUp"
    fault = find(root, "folder:fault-handler")
    assert fault is not None and fault.label == "Controller Fault Handler"
    assert fault.children[0].key == "folder:fault-handler/program:FaultProg"
    # Handler programs live there and nowhere else.
    assert find(root, "task:MainTask/program:PowerUp") is None
    assert find(root, "unscheduled/program:PowerUp") is None
    # No handler attributes on the controller: no folders.
    assert find(empty_root, "folder:powerup-handler") is None
    assert find(empty_root, "folder:fault-handler") is None


def test_unscheduled_programs_inside_tasks_section(root, l5x):
    tasks = find(root, "folder:tasks")
    unsched = find(tasks, "folder:unscheduled")
    assert unsched is not None and unsched.label == "Unscheduled Programs"
    assert unsched in tasks.children  # Studio places Unscheduled under Tasks
    assert [c.key for c in unsched.children] == ["unscheduled/program:Lonely"]
    assert find(unsched, "unscheduled/program:Lonely/routine:LMain") is not None
    # Every program scheduled -> no Unscheduled node at all.
    doc = l5x.parse_string(
        make_l5x(
            body="<Programs>"
            '<Program Name="Only"><Routines/></Program></Programs>'
            "<Tasks>"
            '<Task Name="T" Type="CONTINUOUS">'
            '<ScheduledPrograms><ScheduledProgram Name="Only"/></ScheduledPrograms>'
            "</Task></Tasks>"
        )
    )
    all_scheduled = build_project_tree(doc, ChangeSet()).root
    assert find(all_scheduled, "folder:unscheduled") is None


def test_datatype_subfolders(root):
    dt = find(root, "folder:datatypes")
    assert dt is not None
    assert [c.key for c in dt.children] == [
        "folder:datatypes/user-defined",
        "folder:datatypes/strings",
        "folder:datatypes/add-on-defined",
    ]
    assert all(c.kind == "folder" for c in dt.children)
    user, strings, aoi_defined = dt.children
    assert [n.key for n in user.children] == ["datatype:DemoUDT"]
    assert [n.key for n in strings.children] == ["datatype:MyString"]
    assert [n.key for n in aoi_defined.children] == ["datatype:aoi:ValveCtl"]
    assert all(
        n.kind == "datatype" for sub in dt.children for n in sub.children
    )


def test_datatype_subfolders_shown_only_when_nonempty(l5x):
    # Only a string type and no AOIs: just the Strings subfolder appears.
    doc = l5x.parse_string(
        make_l5x(
            body='<DataTypes><DataType Name="S" Family="StringFamily"/></DataTypes>'
        )
    )
    dt = find(build_project_tree(doc, ChangeSet()).root, "folder:datatypes")
    assert [c.key for c in dt.children] == ["folder:datatypes/strings"]


def test_aoi_routine_children_have_no_ladder_identity(root):
    aoi = find(root, "aoi:ValveCtl")
    assert aoi is not None and aoi.kind == "aoi"
    assert [c.key for c in aoi.children] == ["aoi:ValveCtl/routine:Logic"]
    rt = aoi.children[0]
    assert rt.kind == "routine" and rt.routine_type == "RLL"
    # No ladder-diff card exists for an AOI routine: identity stays unset.
    assert rt.controller is None and rt.program is None and rt.routine is None


def test_motion_group_nesting_and_orphan_axis(root):
    motion = find(root, "folder:motion")
    assert motion is not None
    group = find(motion, "motion:MG1")
    assert group is not None and group.kind == "tag"
    assert [c.key for c in group.children] == ["motion:MG1/axis:AxisA"]
    assert group.children[0].kind == "tag"
    # The orphan axis (its group is not in the file) renders flat, childless.
    orphan = find(motion, "motion:GhostGroup/axis:AxisOrphan")
    assert orphan is not None and orphan in motion.children
    assert orphan.children == []
    # Motion tags are tags: they also stay under Controller Tags.
    tags = find(root, "folder:tags")
    for tag_key in ("tag:MG1", "tag:AxisA", "tag:AxisOrphan"):
        assert find(tags, tag_key) is not None


def test_motion_folder_absent_without_motion_tags(empty_root):
    assert find(empty_root, "folder:motion") is None


# --- diff/status semantics along the new paths --------------------------------


def test_status_rolls_up_through_the_task(l5x):
    old = l5x.parse_string(ORGANIZER)
    new = l5x.parse_string(ORGANIZER_EDIT)
    root = build_project_tree(new, diff_documents(old, new), base_doc=old).root
    rt = find(root, "task:MainTask/program:MixerProg/routine:Main")
    assert rt.status == "modified"
    assert find(root, "task:MainTask").descendant_changed is True
    assert find(root, "folder:tasks").descendant_changed is True
    assert find(root, "task:SideTask").descendant_changed is False


def test_removed_program_attaches_under_its_base_task(l5x):
    old = l5x.parse_string(ORGANIZER)
    new = l5x.parse_string(ORGANIZER_NO_ZETA)
    root = build_project_tree(new, diff_documents(old, new), base_doc=old).root
    phantom = find(root, "task:MainTask/program:Zeta")
    assert phantom is not None and phantom.status == "removed"
    assert phantom.program == "Zeta"
    # The live schedule keeps its order; the phantom is appended after it.
    task = find(root, "task:MainTask")
    assert [c.key for c in task.children] == [
        "task:MainTask/program:MixerProg",
        "task:MainTask/program:Alpha",
        "task:MainTask/program:Zeta",
    ]
    assert task.descendant_changed is True
    assert find(root, "unscheduled/program:Zeta") is None


def test_removed_task_phantom_holds_its_removed_programs(l5x):
    old = l5x.parse_string(ORGANIZER)
    new = l5x.parse_string(ORGANIZER_NO_SIDETASK)
    root = build_project_tree(new, diff_documents(old, new), base_doc=old).root
    task = find(root, "task:SideTask")
    assert task is not None and task.status == "removed"
    assert [c.key for c in task.children] == ["task:SideTask/program:SideProg"]
    assert task.children[0].status == "removed"


def test_removed_program_without_base_doc_lands_in_unscheduled(l5x):
    old = l5x.parse_string(ORGANIZER)
    new = l5x.parse_string(ORGANIZER_NO_ZETA)
    root = build_project_tree(new, diff_documents(old, new)).root  # no base_doc
    phantom = find(root, "unscheduled/program:Zeta")
    assert phantom is not None and phantom.status == "removed"
    assert find(root, "task:MainTask/program:Zeta") is None


def test_moved_program_flags_both_tasks_but_renders_once(l5x):
    def sched_doc(t1: str, t2: str) -> str:
        return make_l5x(
            body="<Programs>"
            '<Program Name="Mover">'
            '<Routines><Routine Name="Main" Type="RLL"><RLLContent/></Routine></Routines>'
            "</Program></Programs>"
            "<Tasks>"
            f'<Task Name="T1" Type="CONTINUOUS">{t1}</Task>'
            f'<Task Name="T2" Type="PERIODIC" Rate="10">{t2}</Task>'
            "</Tasks>"
        )

    schedule = '<ScheduledPrograms><ScheduledProgram Name="Mover"/></ScheduledPrograms>'
    old = l5x.parse_string(sched_doc(schedule, ""))
    new = l5x.parse_string(sched_doc("", schedule))
    root = build_project_tree(new, diff_documents(old, new), base_doc=old).root
    # The subtree renders under the head-ref task only.
    assert find(root, "task:T2/program:Mover") is not None
    assert find(root, "task:T1/program:Mover") is None
    assert program_names(root) == ["Mover"]
    # But the move counts as a change on BOTH tasks.
    t1, t2 = find(root, "task:T1"), find(root, "task:T2")
    assert t1.status == "modified" and t2.status == "modified"
    assert t1.descendant_changed is True
    assert t2.descendant_changed is True
