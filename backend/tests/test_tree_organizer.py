"""Organizer-tree structure added in schema v3: Data Types subfolders, AOI
routine children, Motion Groups, Power-Up / Controller Fault Handler folders,
and task program references carrying the program's routine subtree."""
import pytest

from app.tree import SCHEMA_VERSION, TreeNode, build_project_tree
from diff import diff_documents
from diff.models import ChangeSet
from fixtures_l5x import make_l5x

# One document exercising every new organizer category: a UDT and a string
# type, an AOI with a routine, a motion group with one grouped and one orphan
# axis, both controller handler programs, and a task scheduling a program.
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
        '<Program Name="PowerUp">'
        '<Routines><Routine Name="Boot" Type="RLL"><RLLContent/></Routine></Routines>'
        "</Program>"
        '<Program Name="FaultProg"><Routines/></Program>'
        "</Programs>"
        "<Tasks>"
        '<Task Name="MainTask" Type="CONTINUOUS">'
        '<ScheduledPrograms><ScheduledProgram Name="MixerProg"/></ScheduledPrograms>'
        "</Task>"
        "</Tasks>"
    ),
)

# The same document with the one rung edited — for status-overlay tests.
ORGANIZER_EDIT = ORGANIZER.replace(
    "XIC(PlainTag)OTE(PlainTag);", "XIC(PlainTag)XIC(PlainTag)OTE(PlainTag);"
)


def find(node: TreeNode, key: str) -> TreeNode | None:
    """Depth-first search of the tree for the node with `key`."""
    if node.key == key:
        return node
    for child in node.children:
        if (hit := find(child, key)) is not None:
            return hit
    return None


@pytest.fixture(scope="module")
def root(l5x) -> TreeNode:
    return build_project_tree(l5x.parse_string(ORGANIZER), ChangeSet()).root


@pytest.fixture(scope="module")
def empty_root(l5x) -> TreeNode:
    """A document with no motion tags and no handler attributes."""
    return build_project_tree(l5x.parse_string(make_l5x()), ChangeSet()).root


def test_schema_version_bumped(l5x):
    assert SCHEMA_VERSION == 3
    tree = build_project_tree(l5x.parse_string(ORGANIZER), ChangeSet())
    assert tree.schema_version == 3


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


def test_handler_folders(root, empty_root):
    powerup = find(root, "folder:powerup-handler")
    assert powerup is not None and powerup.label == "Power-Up Handler"
    ref = powerup.children[0]
    assert ref.key == "folder:powerup-handler/program:PowerUp"
    assert ref.kind == "program" and ref.program == "PowerUp"
    fault = find(root, "folder:fault-handler")
    assert fault is not None and fault.label == "Controller Fault Handler"
    assert fault.children[0].key == "folder:fault-handler/program:FaultProg"
    # No handler attributes on the controller: no folders.
    assert find(empty_root, "folder:powerup-handler") is None
    assert find(empty_root, "folder:fault-handler") is None


def test_task_program_carries_routine_subtree(root):
    ref = find(root, "task:MainTask/program:MixerProg")
    assert ref is not None and ref.kind == "program"
    assert [c.key for c in ref.children] == [
        "task:MainTask/program:MixerProg/routine:Main"
    ]
    rt = ref.children[0]
    # Task-nested routines DO map to real ladder cards.
    assert rt.kind == "routine" and rt.routine_type == "RLL"
    assert rt.controller == "ctrllr" and rt.program == "MixerProg" and rt.routine == "Main"


def test_flat_programs_folder_unchanged(root):
    """The frontend still relies on the flat Programs folder and its keys."""
    prog = find(root, "program:MixerProg")
    assert prog is not None and prog.kind == "program"
    rt = find(prog, "program:MixerProg/routine:Main")
    assert rt is not None
    assert rt.controller == "ctrllr" and rt.program == "MixerProg" and rt.routine == "Main"


def test_status_overlays_reach_both_routine_copies(l5x):
    old = l5x.parse_string(ORGANIZER)
    new = l5x.parse_string(ORGANIZER_EDIT)
    root = build_project_tree(new, diff_documents(old, new)).root
    flat = find(root, "program:MixerProg/routine:Main")
    nested = find(root, "task:MainTask/program:MixerProg/routine:Main")
    assert flat.status == "modified"
    assert nested.status == "modified"
    # The change rolls up through the task folder like any other descendant.
    assert find(root, "folder:tasks").descendant_changed is True
    assert find(root, "folder:programs").descendant_changed is True
