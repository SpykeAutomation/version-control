"""End-to-end tests for program, routine, and task parsing."""
from fixtures_l5x import make_l5x


def parse_program(l5x, program_xml: str):
    doc = l5x.parse_string(make_l5x(body=f"<Programs>{program_xml}</Programs>"))
    assert len(doc.programs) == 1
    return doc.programs[0]


def parse_routine(l5x, routine_xml: str):
    program = parse_program(
        l5x, f'<Program Name="MixerProg"><Routines>{routine_xml}</Routines></Program>'
    )
    assert len(program.routines) == 1
    return program.routines[0]


def parse_task(l5x, task_xml: str):
    doc = l5x.parse_string(make_l5x(body=f"<Tasks>{task_xml}</Tasks>"))
    assert len(doc.tasks) == 1
    return doc.tasks[0]


# ---------------------------------------------------------------------------
# Programs
# ---------------------------------------------------------------------------


def test_program_attributes(l5x):
    program = parse_program(
        l5x,
        '<Program Name="MixerProg" TestEdits="true" MainRoutineName="Main"'
        ' FaultRoutineName="Fault" Disabled="true" UseAsFolder="false" Class="Standard">'
        "<Description>Mixer sequencing</Description>"
        "</Program>",
    )
    assert program.name == "MixerProg"
    assert program.test_edits is True
    assert program.main_routine_name == "Main"
    assert program.fault_routine_name == "Fault"
    assert program.disabled is True
    assert program.use_as_folder is False
    assert program.program_class == "Standard"
    assert program.description == "Mixer sequencing"


def test_child_programs(l5x):
    program = parse_program(
        l5x,
        '<Program Name="ParentProg" UseAsFolder="true">'
        "<ChildPrograms>"
        '<ChildProgram Name="ChildA"/><ChildProgram Name="ChildB"/>'
        "</ChildPrograms></Program>",
    )
    assert program.use_as_folder is True
    assert program.child_programs == ["ChildA", "ChildB"]


def test_program_custom_properties(l5x):
    program = parse_program(
        l5x,
        '<Program Name="LibProg">'
        "<CustomProperties><Versions><Maj>1</Maj></Versions></CustomProperties>"
        "</Program>",
    )
    assert program.custom_properties == {"Versions.Maj.#text": "1"}


# ---------------------------------------------------------------------------
# Routines
# ---------------------------------------------------------------------------


def test_rll_routine_rungs(l5x):
    routine = parse_routine(
        l5x,
        '<Routine Name="Main" Type="RLL">'
        "<Description>main sequence</Description>"
        "<RLLContent>"
        '<Rung Number="0" Type="N"><Comment>start gate</Comment>'
        "<Text>XIC(StartPB)OTE(RunLamp);</Text></Rung>"
        '<Rung Number="1" Type="N"><Text>NOP();</Text></Rung>'
        "</RLLContent></Routine>",
    )
    assert routine.type == "RLL"
    assert routine.description == "main sequence"
    assert routine.encoded is False
    r0, r1 = routine.content.rungs
    assert (r0.number, r0.type, r0.comment) == (0, "N", "start gate")
    assert r0.text == "XIC(StartPB)OTE(RunLamp);"
    assert r1.number == 1
    assert routine.content.lines is None
    assert routine.content.raw_xml is None


def test_st_routine_with_text_child(l5x):
    routine = parse_routine(
        l5x,
        '<Routine Name="Calc" Type="ST"><STContent>'
        '<Line Number="0"><Text>StepNo := 1;</Text></Line>'
        '<Line Number="1"><Text>NOP();</Text></Line>'
        "</STContent></Routine>",
    )
    l0, l1 = routine.content.lines
    assert (l0.number, l0.text) == (0, "StepNo := 1;")
    assert (l1.number, l1.text) == (1, "NOP();")


def test_st_routine_with_direct_line_text(l5x):
    routine = parse_routine(
        l5x,
        '<Routine Name="Calc" Type="ST"><STContent>'
        '<Line Number="0" Level="1">StepNo := 2;</Line>'
        "</STContent></Routine>",
    )
    line = routine.content.lines[0]
    assert line.level == 1
    assert line.text == "StepNo := 2;"


def test_fbd_routine_preserved_as_raw_xml(l5x):
    routine = parse_routine(
        l5x,
        '<Routine Name="Blend" Type="FBD">'
        '<FBDContent SheetSize="Letter"><Sheet Number="1"/></FBDContent>'
        "</Routine>",
    )
    assert routine.content.rungs is None
    assert routine.content.lines is None
    assert "FBDContent" in routine.content.raw_xml
    assert 'SheetSize="Letter"' in routine.content.raw_xml


def test_sfc_routine_preserved_as_raw_xml(l5x):
    routine = parse_routine(
        l5x,
        '<Routine Name="Phases" Type="SFC"><SFCContent><Step Name="Init"/></SFCContent></Routine>',
    )
    assert "SFCContent" in routine.content.raw_xml


def test_routine_with_no_content_element(l5x):
    routine = parse_routine(l5x, '<Routine Name="Empty" Type="RLL"/>')
    assert routine.content.rungs is None
    assert routine.content.lines is None
    assert routine.content.raw_xml is None


def test_encoded_routine(l5x):
    routine = parse_routine(
        l5x,
        '<EncodedData EncodedType="Routine" Name="ProtCalc" Type="ST" EncryptionConfig="2">'
        "<Description>protected calc</Description>"
        "<CustomProperties><Versions><Maj>3</Maj></Versions></CustomProperties>"
        "ZW5jb2RlZC1ibG9i"
        "</EncodedData>",
    )
    assert routine.encoded is True
    assert routine.name == "ProtCalc"
    assert routine.type == "ST"
    assert routine.encryption_config == "2"
    assert routine.description == "protected calc"
    assert routine.custom_properties == {"Versions.Maj.#text": "3"}
    assert routine.content.rungs is None
    assert routine.content.lines is None
    assert "ZW5jb2RlZC1ibG9i" not in routine.model_dump_json()


def test_plain_and_encoded_routines_in_one_container(l5x):
    program = parse_program(
        l5x,
        '<Program Name="MixerProg"><Routines>'
        '<Routine Name="Main" Type="RLL"/>'
        '<EncodedData EncodedType="Routine" Name="ProtCalc"/>'
        "</Routines></Program>",
    )
    assert [(r.name, r.encoded) for r in program.routines] == [
        ("Main", False),
        ("ProtCalc", True),
    ]
    # EncodedType defaults the routine type to RLL when absent.
    assert program.routines[1].type == "RLL"


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


def test_continuous_task_defaults(l5x):
    task = parse_task(l5x, '<Task Name="MainTask" Type="CONTINUOUS" Watchdog="500"/>')
    assert task.type == "CONTINUOUS"
    assert task.rate is None
    assert task.watchdog == 500.0
    assert task.event_info is None
    assert task.scheduled_programs == []


def test_periodic_task(l5x):
    task = parse_task(
        l5x,
        '<Task Name="ScanTask" Type="PERIODIC" Rate="10.5" Priority="7" Watchdog="500"'
        ' DisableUpdateOutputs="true" InhibitTask="true" Class="Safety">'
        "<Description>fast scan</Description>"
        "<ScheduledPrograms>"
        '<ScheduledProgram Name="MixerProg"/><ScheduledProgram Name="FillerProg"/>'
        "</ScheduledPrograms></Task>",
    )
    assert task.type == "PERIODIC"
    assert task.rate == 10.5
    assert task.priority == 7
    assert task.disable_update_outputs is True
    assert task.inhibit_task is True
    assert task.task_class == "Safety"
    assert task.description == "fast scan"
    assert task.scheduled_programs == ["MixerProg", "FillerProg"]


def test_event_task(l5x):
    task = parse_task(
        l5x,
        '<Task Name="EvtTask" Type="EVENT" Priority="5" Watchdog="500">'
        '<EventInfo EventType="Tag" EventTag="TriggerTag" Timeout="2000.0" EventOnReset="true"/>'
        "</Task>",
    )
    ei = task.event_info
    assert ei.event_type == "Tag"
    assert ei.event_tag == "TriggerTag"
    assert ei.timeout == 2000.0
    assert ei.event_on_reset is True


def test_event_info_ignored_for_non_event_task(l5x):
    task = parse_task(
        l5x,
        '<Task Name="ScanTask" Type="PERIODIC" Rate="10">'
        '<EventInfo EventType="Tag" EventTag="TriggerTag"/>'
        "</Task>",
    )
    assert task.event_info is None
