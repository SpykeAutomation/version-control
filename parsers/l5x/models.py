"""
Pydantic models representing the structured output of a parsed L5X file.

Each model maps to a logical entity in a Rockwell Studio 5000 project:
controller metadata, data types (UDTs), add-on instructions (AOIs),
tags, programs/routines, and tasks.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Produced / Consumed tag connection properties
# ---------------------------------------------------------------------------


class ProducedTagConnection(BaseModel):
    """Connection properties from a <ProduceInfo> element."""

    produce_count: Optional[int] = None                  # ProduceCount
    programmatically_send_event_trigger: bool = False    # ProgrammaticallySendEventTrigger
    unicast_permitted: bool = False                      # UnicastPermitted
    min_rpi: Optional[float] = None                     # MinimumRPI
    max_rpi: Optional[float] = None                     # MaximumRPI
    default_rpi: Optional[float] = None                 # DefaultRPI


class ConsumedTagConnection(BaseModel):
    """Connection properties from a <ConsumeInfo> element."""

    producer: Optional[str] = None                       # Producer (controller name)
    remote_tag: Optional[str] = None                     # RemoteTag
    remote_instance: Optional[int] = None                # RemoteInstance
    rpi: Optional[float] = None                          # RPI
    unicast: Optional[bool] = None                       # Unicast
    # Safety-only fields
    timeout_multiplier: Optional[int] = None             # TimeoutMultiplier
    network_delay_multiplier: Optional[int] = None       # NetworkDelayMultiplier
    reaction_time_limit: Optional[float] = None          # ReactionTimeLimit
    max_observed_network_delay: Optional[float] = None   # MaxObservedNetworkDelay


# ---------------------------------------------------------------------------
# Event task trigger configuration
# ---------------------------------------------------------------------------


class EventInfo(BaseModel):
    """Trigger configuration from a Task's <EventInfo> child element."""

    event_type: Optional[str] = None          # e.g. EVENT_CONSUMED_TAG_DATA_UPDATE
    event_tag: Optional[str] = None           # tag name for consumed-tag / EVENT triggers
    module_name: Optional[str] = None         # module name for module-input triggers
    module_input_specifier: Optional[str] = None  # point/bit specifier on the module
    timeout: Optional[float] = None           # fallback run timeout in ms; 0 = disabled
    event_on_reset: bool = False


# ---------------------------------------------------------------------------
# Metadata & Controller
# ---------------------------------------------------------------------------


class ControllerMetadata(BaseModel):
    """Top-level attributes from the RSLogix5000Content root element."""

    schema_revision: Optional[str] = None
    software_revision: Optional[str] = None
    target_name: Optional[str] = None
    target_type: Optional[str] = None
    contains_context: Optional[bool] = None
    export_date: Optional[str] = None
    export_options: Optional[str] = None
    converted_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class SafetyInfo(BaseModel):
    safety_locked: bool = False
    signature_run_mode_protect: bool = False
    configure_safety_io_always: bool = False
    safety_level: Optional[str] = None       # e.g. "SIL2/PLd"
    safety_tag_map: Optional[str] = None     # raw tag mapping string


class RedundancyInfo(BaseModel):
    enabled: bool = False
    keep_test_edits_on_switch_over: bool = False


class Security(BaseModel):
    code: int = 0
    changes_to_detect: Optional[str] = None  # hex bitmask string


class TimeSynchronize(BaseModel):
    priority1: Optional[int] = None
    priority2: Optional[int] = None
    ptp_enable: bool = False


class Controller(BaseModel):
    """Full controller attributes including safety, redundancy, and sync config."""

    name: str
    processor_type: Optional[str] = None
    major_rev: Optional[int] = None
    minor_rev: Optional[int] = None
    time_slice: Optional[int] = None
    project_creation_date: Optional[str] = None
    last_modified_date: Optional[str] = None
    comm_path: Optional[str] = None
    project_sn: Optional[str] = None
    match_project_to_controller: bool = False
    can_use_rpi_from_producer: bool = False
    inhibit_automatic_firmware_update: int = 0
    pass_through_configuration: Optional[str] = None
    download_project_documentation_and_extended_properties: bool = False
    download_project_custom_properties: bool = False
    report_minor_overflow: bool = False
    auto_diags_enabled: bool = False
    web_server_enabled: bool = False
    power_loss_program: Optional[str] = None
    fault_handler_program: Optional[str] = None  # MajorFaultProgram attribute
    ignore_array_faults_during_postscan: bool = False
    sfc_execution_control: Optional[str] = None
    sfc_last_scan: Optional[str] = None
    sfc_restart_position: Optional[str] = None
    description: Optional[str] = None
    safety_info: Optional[SafetyInfo] = None
    redundancy_info: Optional[RedundancyInfo] = None
    security: Optional[Security] = None
    time_synchronize: Optional[TimeSynchronize] = None


# ---------------------------------------------------------------------------
# Data Types (UDTs)
# ---------------------------------------------------------------------------


class UDTMember(BaseModel):
    name: str
    data_type: str
    dimension: int = 0
    radix: Optional[str] = None
    hidden: bool = False
    external_access: Optional[str] = None
    description: Optional[str] = None
    # BIT-type members reference a target tag and bit position
    target: Optional[str] = None
    bit_number: Optional[int] = None


class DataType(BaseModel):
    name: str
    family: Optional[str] = None
    udt_class: Optional[str] = None  # 'class' is a Python keyword
    description: Optional[str] = None
    members: list[UDTMember] = []


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


class MessageConfig(BaseModel):
    """Configuration extracted from a MESSAGE tag's MessageParameters element."""
    message_type: Optional[str] = None     # e.g. "CIP Generic", "CIP Data Table Read"
    destination_tag: Optional[str] = None  # local tag written by MSG GET/read
    source_tag: Optional[str] = None       # local tag read by MSG PUT/write
    service_code: Optional[str] = None     # e.g. "16#000e" (Get Attribute Single)


class Tag(BaseModel):
    name: str
    scope: str  # "controller" or the program name for program-scoped tags
    tag_type: Optional[str] = None  # Base, Alias, Produced, Consumed
    data_type: str
    dimensions: Optional[list[int]] = None
    radix: Optional[str] = None
    constant: bool = False
    external_access: Optional[str] = None
    description: Optional[str] = None
    value: Optional[str] = None  # Raw L5K value for scalar/simple types
    tag_class: Optional[str] = None  # "Safety" for safety tags; absent/None for standard
    produced_connection: Optional[ProducedTagConnection] = None
    consumed_connection: Optional[ConsumedTagConnection] = None
    message_config: Optional[MessageConfig] = None  # populated for MESSAGE tags


# ---------------------------------------------------------------------------
# Modules
# ---------------------------------------------------------------------------


class ModulePort(BaseModel):
    id: int
    type: Optional[str] = None       # ICP, Ethernet, PointIO, etc.
    address: Optional[str] = None    # IP address or slot number
    upstream: bool = False
    safety_network: Optional[str] = None
    bus_size: Optional[int] = None   # number of slots on the bus


class Module(BaseModel):
    name: str
    catalog_number: Optional[str] = None
    vendor: Optional[int] = None
    product_type: Optional[int] = None
    product_code: Optional[int] = None
    major: Optional[int] = None
    minor: Optional[int] = None
    parent_module: Optional[str] = None
    parent_mod_port_id: Optional[int] = None
    inhibited: bool = False
    major_fault: bool = False
    safety_network: Optional[str] = None
    ekey_state: Optional[str] = None  # Disabled, CompatibleModule, ExactMatch
    ports: list[ModulePort] = []


# ---------------------------------------------------------------------------
# Add-On Instructions (AOIs)
# ---------------------------------------------------------------------------


class AOIParameter(BaseModel):
    name: str
    tag_type: Optional[str] = None  # Input, Output, InOut
    data_type: str
    usage: Optional[str] = None
    radix: Optional[str] = None
    required: bool = False
    visible: bool = True
    external_access: Optional[str] = None
    description: Optional[str] = None
    alias_for: Optional[str] = None  # local tag (or member) this param is an alias for


class AOILocalTag(BaseModel):
    name: str
    data_type: str
    dimensions: Optional[list[int]] = None
    radix: Optional[str] = None
    external_access: Optional[str] = None
    description: Optional[str] = None


# ---------------------------------------------------------------------------
# Routines
# ---------------------------------------------------------------------------


class Rung(BaseModel):
    """A single rung in a Ladder Logic (RLL) routine."""

    number: int
    type: Optional[str] = None  # N=Normal, C=Comment
    comment: Optional[str] = None
    text: Optional[str] = None  # Raw rung text, e.g. "XIC(Tag1)OTE(Tag2);"


class STLine(BaseModel):
    """A single line in a Structured Text (ST) routine."""

    number: int
    level: int = 0  # Indentation level
    text: str = ""


class RoutineContent(BaseModel):
    """
    Union-style container for routine content.
    Exactly one field will be populated depending on the routine type:
      - rungs  → RLL (Ladder Logic)
      - lines  → ST  (Structured Text)
      - raw_xml → FBD / SFC (preserved as-is for future parsing)
    """

    rungs: Optional[list[Rung]] = None
    lines: Optional[list[STLine]] = None
    raw_xml: Optional[str] = None


class Routine(BaseModel):
    name: str
    type: str  # RLL, ST, FBD, SFC
    description: Optional[str] = None
    content: RoutineContent


# ---------------------------------------------------------------------------
# AOI (full definition)
# ---------------------------------------------------------------------------


class AOI(BaseModel):
    name: str
    aoi_class: Optional[str] = None  # "Safety" for safety AOIs; absent/None for standard
    revision: Optional[str] = None
    revision_extension: Optional[str] = None
    vendor: Optional[str] = None
    execute_prescan: bool = False
    execute_postscan: bool = False
    execute_enable_in_false: bool = False
    created_date: Optional[str] = None
    created_by: Optional[str] = None
    edited_date: Optional[str] = None
    edited_by: Optional[str] = None
    software_revision: Optional[str] = None
    description: Optional[str] = None
    parameters: list[AOIParameter] = []
    local_tags: list[AOILocalTag] = []
    routines: list[Routine] = []


# ---------------------------------------------------------------------------
# Programs
# ---------------------------------------------------------------------------


class Program(BaseModel):
    name: str
    description: Optional[str] = None
    test_edits: bool = False
    main_routine_name: Optional[str] = None
    fault_routine_name: Optional[str] = None
    disabled: bool = False
    use_as_folder: bool = False
    program_class: Optional[str] = None  # "Standard" or "Safety"
    tags: list[Tag] = []
    routines: list[Routine] = []


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


class Task(BaseModel):
    name: str
    type: str  # CONTINUOUS, PERIODIC, EVENT
    rate: Optional[float] = None
    priority: Optional[int] = None
    watchdog: Optional[float] = None
    disable_update_outputs: bool = False
    inhibit_task: bool = False
    task_class: Optional[str] = None  # "Standard" or "Safety"
    scheduled_programs: list[str] = []
    event_info: Optional[EventInfo] = None  # populated for EVENT tasks only


# ---------------------------------------------------------------------------
# Top-level document
# ---------------------------------------------------------------------------


class L5XDocument(BaseModel):
    """
    The complete parsed representation of an L5X file.
    Serialises directly to JSON via .model_dump_json().
    """

    metadata: ControllerMetadata
    controller: Controller
    modules: list[Module] = []
    data_types: list[DataType] = []
    add_on_instructions: list[AOI] = []
    controller_tags: list[Tag] = []
    programs: list[Program] = []
    tasks: list[Task] = []
