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
    # SafetySignature — Rockwell's fingerprint of the entire safety
    # application (the value an auditor checks to confirm the safety logic is
    # unchanged). Absent when no signature has been generated.
    safety_signature: Optional[str] = None
    # Lock/unlock passwords export as encrypted strings whose encoding is
    # deterministic — identical across exports of an unchanged project. The
    # ciphertext itself is credential material, so it is never stored; only a
    # SHA-256 fingerprint is kept. The fingerprint changes iff the underlying
    # ciphertext changes, which preserves "diff detects a password change"
    # without persisting the credential into version-control history.
    safety_lock_password_fingerprint: Optional[str] = None
    safety_unlock_password_fingerprint: Optional[str] = None


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


class CST(BaseModel):
    """Coordinated System Time config from the controller's <CST> element.

    MasterID names the CST master on the backplane (0 = no master / this
    controller is not a time master). A change rewires time coordination."""

    master_id: Optional[int] = None  # MasterID


class WallClockTime(BaseModel):
    """Controller real-time-clock config from the <WallClockTime> element."""

    local_time_adjustment: Optional[int] = None  # LocalTimeAdjustment (microseconds)
    time_zone: Optional[int] = None              # TimeZone (offset, minutes)


class EthernetPort(BaseModel):
    """One onboard Ethernet port from the controller's <EthernetPorts> list.

    Distinct from a module <Port>: these are the controller's own physical
    ports, carrying the per-port enable flag and dual-port label."""

    port: Optional[int] = None       # Port (1, 2, ...)
    label: Optional[str] = None      # Label (e.g. "A1")
    port_enabled: bool = False       # PortEnabled


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
    cst: Optional[CST] = None
    wall_clock_time: Optional[WallClockTime] = None
    ethernet_ports: list[EthernetPort] = []


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


class Tag(BaseModel):
    name: str
    scope: str  # "controller" or the program name for program-scoped tags
    tag_type: Optional[str] = None  # Base, Alias, Produced, Consumed
    # Target an Alias tag points at, from the AliasFor attribute (a module I/O
    # point, another tag, or a UDT member / array element). This is the defining
    # property of an alias — an alias carries no value of its own, so a change
    # here silently rewires which tag or I/O point the logic reads/writes. None
    # for non-alias tags.
    alias_for: Optional[str] = None
    # How a program-scoped tag participates in its program's interface, from the
    # Usage attribute: Input / Output / InOut / Public expose the tag as a program
    # parameter; Normal is a plain local tag. A change here rewires the program's
    # I/O surface. None for controller-scoped tags without a Usage.
    usage: Optional[str] = None
    data_type: str
    dimensions: Optional[list[int]] = None
    radix: Optional[str] = None
    constant: bool = False
    external_access: Optional[str] = None
    description: Optional[str] = None
    value: Optional[str] = None  # Single scalar/string value (None for structured tags)
    # Flat {member_path: value} for UDT / array tags, decoded from the Decorated
    # data block. Paths use dots for members and [i] for array indices, e.g.
    # {"ParentMember.ChildMember": "<value>", "SomeArray[0]": "<value>"}. STRING
    # members are collapsed to their text. Empty for plain scalar tags. For diffing.
    values: dict[str, str] = {}
    # Flat {parameter: value} map of motion configuration, read from a
    # <Data Format="Axis"> or <Data Format="MotionGroup"> block (AXIS_* and
    # MOTION_GROUP tags). Every parameter is an XML attribute on a single child
    # element, captured verbatim as strings for diffing. Empty for non-motion tags.
    motion_config: dict[str, str] = {}
    # Flat {parameter: value} map of MSG instruction configuration, read
    # verbatim from a MESSAGE tag's <Data Format="Message">/<MessageParameters>
    # block (same shape as motion_config). Everything the engineer sets in the
    # MSG dialog lives here: MessageType, ConnectionPath (which device the
    # message talks to), Remote/LocalElement, RequestedLength, ServiceCode,
    # ObjectType, AttributeNumber, CacheConnections, ... Empty for
    # non-MESSAGE tags.
    message_config: dict[str, str] = {}
    # {operand: comment} per-bit/per-member comments from the tag's <Comments>
    # block; operand is the raw attribute, e.g. ".0", ".STATE", "[0]". Empty
    # when the tag has no operand comments.
    comments: dict[str, str] = {}
    tag_class: Optional[str] = None  # "Safety" for safety tags; absent/None for standard
    produced_connection: Optional[ProducedTagConnection] = None
    consumed_connection: Optional[ConsumedTagConnection] = None


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
    width: Optional[int] = None      # Width — slots the module occupies on the bus


class ModuleConnection(BaseModel):
    """
    One <Connection> under a module's <Communications> element: the I/O
    connection configuration an engineer tunes (RPI, data sizes, production
    trigger, connection path). The safety-timing fields mirror those on
    ConsumedTagConnection and populate only for safety connections.
    """

    name: Optional[str] = None                     # Name
    rpi: Optional[int] = None                       # RPI (microseconds)
    type: Optional[str] = None                      # Input, Output, StandardDataDriven, ...
    input_size: Optional[int] = None                # InputSize
    output_size: Optional[int] = None               # OutputSize
    input_cxn_point: Optional[int] = None           # InputCxnPoint
    output_cxn_point: Optional[int] = None          # OutputCxnPoint
    priority: Optional[str] = None                  # Priority (e.g. Scheduled)
    input_connection_type: Optional[str] = None     # Multicast / Unicast
    input_production_trigger: Optional[str] = None   # Cyclic / Change Of State / ...
    unicast: Optional[bool] = None                  # Unicast
    event_id: Optional[int] = None                  # EventID
    programmatically_send_event_trigger: bool = False  # ProgrammaticallySendEventTrigger
    connection_path: Optional[str] = None           # ConnectionPath
    input_tag_suffix: Optional[str] = None          # InputTagSuffix (e.g. "I0")
    output_tag_suffix: Optional[str] = None         # OutputTagSuffix (e.g. "O0")
    # Safety-only connection timing
    timeout_multiplier: Optional[int] = None         # TimeoutMultiplier
    network_delay_multiplier: Optional[int] = None   # NetworkDelayMultiplier
    reaction_time_limit: Optional[float] = None      # ReactionTimeLimit
    max_observed_network_delay: Optional[float] = None  # MaxObservedNetworkDelay
    # {operand: comment} per-bit/per-member comments from the connection's
    # <InputTag>/<OutputTag> <Comments> block (the I/O point documentation).
    # Operand is the raw attribute, e.g. ".PT00DATA", ".OUTPUTAREA[0].0".
    input_comments: dict[str, str] = {}
    output_comments: dict[str, str] = {}


class RackConnection(BaseModel):
    """A <RackConnection> under a module's <Communications>. Rack-optimized
    connections carry no tunable attributes here; only the per-operand comments
    on their alias I/O tags are captured (operand = raw attribute, e.g. ".0")."""

    in_alias_comments: dict[str, str] = {}    # <InAliasTag> per-operand comments
    out_alias_comments: dict[str, str] = {}   # <OutAliasTag> per-operand comments


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
    safety_enabled: Optional[bool] = None      # SafetyEnabled
    auto_diags_enabled: Optional[bool] = None  # AutoDiagsEnabled
    # Identity overrides for generic/third-party modules. When CatalogNumber is
    # generic, these UserDefined* attributes define what the device actually is;
    # a change here is effectively a different device.
    user_defined_vendor: Optional[int] = None
    user_defined_product_type: Optional[int] = None
    user_defined_product_code: Optional[int] = None
    user_defined_major: Optional[int] = None
    user_defined_minor: Optional[int] = None
    ekey_state: Optional[str] = None  # Disabled, CompatibleModule, ExactMatch
    ports: list[ModulePort] = []
    # I/O connection configuration from the <Communications> element.
    comm_method: Optional[str] = None   # Communications CommMethod attribute
    # Flat {member_path: value} map of the module's configuration, decoded from
    # a decorated <ConfigTag> block (same shape as Tag.values). Empty when the
    # module has no decorated config tag.
    config_values: dict[str, str] = {}
    # Raw L5K config blob from <ConfigData>, kept as a diff-detectable fallback
    # when no decorated config tag was exported. None when config_values is set.
    config_l5k: Optional[str] = None
    # Opaque L5K config/safety script blobs (<ConfigScript>/<SafetyScript>,
    # siblings of <ConfigData>). Plain L5K text, kept verbatim for diffing.
    config_script_l5k: Optional[str] = None
    safety_script_l5k: Optional[str] = None
    connections: list[ModuleConnection] = []
    rack_connections: list[RackConnection] = []
    # Flattened <ExtendedProperties> subtree as a {dotted_path: value} map
    # (vendor/channel/feedback metadata). Empty when the block is absent.
    extended_properties: dict[str, str] = {}


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
    # Default value(s) from the parameter's DefaultData block. `default_value`
    # holds a scalar/string default; `default_values` is the flat path→value map
    # for structured/array defaults (same shape as Tag.values).
    default_value: Optional[str] = None
    default_values: dict[str, str] = {}
    # {operand: comment} per-bit/per-member comments from the parameter's
    # <Comments> block; operand is the raw attribute, e.g. ".0", ".STATE".
    comments: dict[str, str] = {}


class AOILocalTag(BaseModel):
    name: str
    data_type: str
    dimensions: Optional[list[int]] = None
    radix: Optional[str] = None
    external_access: Optional[str] = None
    description: Optional[str] = None
    default_value: Optional[str] = None       # scalar/string default
    default_values: dict[str, str] = {}        # flat default map for structured local tags
    # {operand: comment} per-bit/per-member comments from the local tag's
    # <Comments> block; operand is the raw attribute, e.g. ".0", ".STATE".
    comments: dict[str, str] = {}


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
    # Source-protected ("encoded") routine exported as <EncodedData
    # EncodedType="Routine">. The implementation ships as an encrypted blob that
    # is re-randomised on every export (non-deterministic encoding), so it is
    # intentionally not stored: it would diff as changed on every export and
    # carries no recoverable value. No signature is emitted at routine level,
    # so an encoded routine's internal logic changes cannot be detected from the
    # export — only its presence and these metadata fields are diffable. `content`
    # is left empty for encoded routines.
    encoded: bool = False
    encryption_config: Optional[str] = None  # EncryptionConfig


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
    revision_note: Optional[str] = None        # <RevisionNote> revision history
    additional_help_text: Optional[str] = None  # <AdditionalHelpText> instruction help
    # Source-protected ("encoded") AOI exported as <EncodedData
    # EncodedType="AddOnInstructionDefinition">. The public interface
    # (description, revision note, parameters) is still exported in clear text
    # and parsed normally; only local tags and routines live inside the
    # encrypted implementation blob (so local_tags/routines are empty here). That
    # blob is re-randomised on every export, so it is deliberately not stored —
    # `signature_id` is Rockwell's deterministic content fingerprint and is the
    # reliable signal for whether the protected implementation changed.
    encoded: bool = False
    signature_id: Optional[str] = None          # SignatureID — protected-content fingerprint
    signature_timestamp: Optional[str] = None   # SignatureTimestamp
    encryption_config: Optional[str] = None     # EncryptionConfig
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
