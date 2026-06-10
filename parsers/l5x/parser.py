"""
L5XParser — converts a Rockwell Studio 5000 L5X (XML) file into a structured
L5XDocument (Pydantic model), ready for JSON serialisation or database storage.

Supported entities
------------------
- Controller metadata (incl. safety, redundancy, security, time sync, CST,
  wall-clock/timezone, and onboard Ethernet ports)
- Modules (I/O tree: adapters, devices, safety modules) with port addresses
- User-defined data types (UDTs)
- Add-on instructions (AOIs) — parameters, local tags, routines
- Controller-scoped and program-scoped tags
- Programs and routines (RLL, ST; FBD/SFC preserved as raw XML)
- Tasks and scheduled-program assignments
"""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import Element
from typing import Optional

from .models import (
    AOI,
    AOILocalTag,
    AOIParameter,
    ConsumedTagConnection,
    Controller,
    ControllerMetadata,
    CST,
    DataType,
    EthernetPort,
    EventInfo,
    Module,
    ModuleConnection,
    ModulePort,
    ProducedTagConnection,
    RackConnection,
    RedundancyInfo,
    SafetyInfo,
    Security,
    TimeSynchronize,
    L5XDocument,
    Program,
    Routine,
    RoutineContent,
    Rung,
    STLine,
    Tag,
    Task,
    UDTMember,
    WallClockTime,
)


# ---------------------------------------------------------------------------
# XML helper utilities
# ---------------------------------------------------------------------------


def _attr(el: Element, name: str, default: Optional[str] = None) -> Optional[str]:
    return el.get(name, default)


def _bool_attr(el: Element, name: str, default: bool = False) -> bool:
    val = el.get(name, "").strip().lower()
    if not val:
        return default
    return val == "true"


def _opt_bool_attr(el: Element, name: str) -> Optional[bool]:
    """Like _bool_attr but returns None (rather than a default) when absent."""
    val = el.get(name)
    if val is None:
        return None
    return val.strip().lower() == "true"


def _int_attr(el: Element, name: str, default: Optional[int] = None) -> Optional[int]:
    val = el.get(name)
    if val is not None:
        try:
            return int(val)
        except ValueError:
            pass
    return default


def _float_attr(
    el: Element, name: str, default: Optional[float] = None
) -> Optional[float]:
    val = el.get(name)
    if val is not None:
        try:
            return float(val)
        except ValueError:
            pass
    return default


def _description(el: Element) -> Optional[str]:
    """Return the text content of a <Description> child element, if present."""
    desc = el.find("Description")
    if desc is not None and desc.text:
        return desc.text.strip()
    return None


def _child_text(el: Element, tag: str) -> Optional[str]:
    """Return the stripped CDATA text of a named child element, or None."""
    child = el.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return None


def _operand_comments(el: Optional[Element]) -> dict[str, str]:
    """Return {operand: comment} from a <Comments> child, or {} if absent.

    Maps each <Comment Operand="...">'s raw Operand attribute (e.g. ".0",
    ".STATE", "[0]", ".OUTPUTAREA[0].0") to its stripped CDATA text. Mirrors
    _description(): per-bit / per-member operand comments on tags, AOI
    parameters/local tags, and module I/O tags. `el` may be None so callers can
    pass an optional element (e.g. a connection's InputTag) without a guard.
    """
    if el is None:
        return {}
    comments_el = el.find("Comments")
    if comments_el is None:
        return {}
    out: dict[str, str] = {}
    for c in comments_el.findall("Comment"):
        operand = c.get("Operand")
        if operand is None:
            continue
        out[operand] = c.text.strip() if c.text else ""
    return out


def _password_fingerprint(ciphertext: Optional[str]) -> Optional[str]:
    """Return a short SHA-256 fingerprint of an exported password ciphertext.

    The ciphertext is credential material and must not be persisted; the
    fingerprint changes iff the ciphertext changes, so a diff still detects a
    password change. Returns None when the attribute is absent.
    """
    if ciphertext is None:
        return None
    return hashlib.sha256(ciphertext.encode("utf-8")).hexdigest()[:16]


def _parse_dimensions(dim_str: Optional[str]) -> Optional[list[int]]:
    """
    Parse a Studio 5000 dimension string into a list of integers.

    Examples
    --------
    "10"      → [10]
    "10 5"    → [10, 5]
    "[10,5]"  → [10, 5]
    "0"       → None  (scalar tag, no real dimensions)
    """
    if not dim_str or dim_str.strip() == "0":
        return None
    cleaned = dim_str.strip("[] ")
    parts = re.split(r"[,\s]+", cleaned)
    try:
        dims = [int(p) for p in parts if p]
        return dims or None
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Decorated-data decoding
#
# A <Data Format="Decorated"> (or <DefaultData Format="Decorated">) block holds
# a tag/parameter's value as a labelled tree. We flatten that tree into a flat
# {member_path: value} map so individual values can be read and diffed.
#
# Node shapes handled:
#   DataValue                       a lone scalar (root of a simple value)
#   DataValueMember                 a named scalar inside a structure
#   Structure / StructureMember     a UDT and its sub-objects
#   Array / ArrayMember             a list (children are Element nodes)
#   Element                         one list slot (scalar, or wraps a Structure)
# STRING structures (LEN + DATA) are collapsed to their text.
#
# Path convention: members joined with ".", array indices appended as "[i]".
# A root scalar's value lands under the key "(value)".
# ---------------------------------------------------------------------------

_ROOT_VALUE_KEY = "(value)"


def _join_path(path: str, name: str) -> str:
    return name if not path else f"{path}.{name}"


def _clean_ascii_string(raw: Optional[str]) -> str:
    """
    Tidy a decorated ASCII string value. The element text is pretty-printed and
    the value is wrapped in single-quote delimiters, e.g. "\\n'text'\\n". Strip
    the surrounding whitespace and one pair of delimiter quotes; characters
    inside the quotes (including spaces) are preserved.
    """
    s = (raw or "").strip()
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
        s = s[1:-1]
    return s


def _string_struct_text(el: Element) -> Optional[str]:
    """
    If `el` is a STRING-style structure (a DATA member with Radix="ASCII",
    alongside a LEN), return its cleaned text; otherwise None. Detection is by
    shape, not type name, so custom string types are handled too.
    """
    for child in el:
        if child.get("Name") == "DATA" and child.get("Radix") == "ASCII":
            return _clean_ascii_string(child.text)
    return None


def _flatten_decorated(el: Element, path: str, out: dict[str, str]) -> None:
    """Recursively flatten a Decorated node into {path: value}."""
    tag = el.tag

    if tag == "DataValue":  # lone scalar
        out[path or _ROOT_VALUE_KEY] = el.get("Value") or ""
        return

    if tag == "DataValueMember":  # named scalar (or string text) in a structure
        member_path = _join_path(path, el.get("Name", ""))
        # A bare ASCII DATA member carries its text as CDATA, not a Value attr.
        if el.get("Value") is None and el.get("Radix") == "ASCII":
            out[member_path] = _clean_ascii_string(el.text)
        else:
            out[member_path] = el.get("Value") or ""
        return

    if tag in ("Structure", "StructureMember"):
        text = _string_struct_text(el)
        if text is not None:  # collapse a STRING structure to its text
            name = el.get("Name")
            key = _join_path(path, name) if name else (path or _ROOT_VALUE_KEY)
            out[key] = text
            return
        name = el.get("Name")  # StructureMember has one; a root Structure does not
        base = _join_path(path, name) if name else path
        for child in el:
            _flatten_decorated(child, base, out)
        return

    if tag in ("Array", "ArrayMember"):
        name = el.get("Name")  # ArrayMember has one; a root Array does not
        base = _join_path(path, name) if name else path
        for child in el:
            _flatten_decorated(child, base, out)
        return

    if tag == "Element":
        elem_path = f"{path}{el.get('Index', '')}"  # Index already looks like "[i]"
        if el.get("Value") is not None:
            out[elem_path] = el.get("Value") or ""
        else:
            for child in el:  # an Element wrapping a Structure
                _flatten_decorated(child, elem_path, out)
        return


def _flatten_xml(el: Element, path: str, out: dict[str, str]) -> None:
    """Recursively flatten an arbitrary element subtree into {dotted_path: value}.

    Unlike _flatten_decorated (which understands Decorated data nodes), this is a
    generic walk for free-form metadata such as <ExtendedProperties>: it emits
    "<path>.@<attr>" for each attribute and "<path>.#text" for element text.
    """
    for name, val in sorted(el.attrib.items()):
        key = f"{path}.@{name}" if path else f"@{name}"
        out[key] = val
    if el.text and el.text.strip():
        out[f"{path}.#text" if path else "#text"] = el.text.strip()
    for child in el:
        child_path = f"{path}.{child.tag}" if path else child.tag
        _flatten_xml(child, child_path, out)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class L5XParser:
    """
    Parse a Rockwell Studio 5000 L5X export file.

    Usage
    -----
    >>> parser = L5XParser()
    >>> doc = parser.parse_file("MyProject.L5X")
    >>> json_str = doc.model_dump_json(indent=2)
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse_file(self, path: str) -> L5XDocument:
        """Parse an L5X file from disk."""
        tree = ET.parse(path)
        return self._parse_root(tree.getroot())

    def parse_string(self, xml_string: str) -> L5XDocument:
        """Parse an L5X document from a string (useful for testing)."""
        return self._parse_root(ET.fromstring(xml_string))

    # ------------------------------------------------------------------
    # Root
    # ------------------------------------------------------------------

    def _parse_root(self, root: Element) -> L5XDocument:
        if root.tag != "RSLogix5000Content":
            raise ValueError(
                f"Expected root element 'RSLogix5000Content', got '{root.tag}'"
            )

        controller_el = root.find("Controller")
        if controller_el is None:
            raise ValueError("No <Controller> element found in L5X document")

        return L5XDocument(
            metadata=self._parse_metadata(root),
            controller=self._parse_controller(controller_el),
            modules=self._parse_modules(controller_el),
            data_types=self._parse_data_types(controller_el),
            add_on_instructions=self._parse_aois(controller_el),
            controller_tags=self._parse_tags(controller_el, scope="controller"),
            programs=self._parse_programs(controller_el),
            tasks=self._parse_tasks(controller_el),
        )

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def _parse_metadata(self, root: Element) -> ControllerMetadata:
        contains_ctx_raw = _attr(root, "ContainsContext", "")
        contains_context: Optional[bool] = (
            None if not contains_ctx_raw
            else contains_ctx_raw.strip().lower() == "true"
        )
        return ControllerMetadata(
            schema_revision=_attr(root, "SchemaRevision"),
            software_revision=_attr(root, "SoftwareRevision"),
            target_name=_attr(root, "TargetName"),
            target_type=_attr(root, "TargetType"),
            contains_context=contains_context,
            export_date=_attr(root, "ExportDate"),
            export_options=_attr(root, "ExportOptions"),
        )

    # ------------------------------------------------------------------
    # Controller
    # ------------------------------------------------------------------

    def _parse_controller(self, el: Element) -> Controller:
        # SafetyInfo
        safety_info = None
        si = el.find("SafetyInfo")
        if si is not None:
            stm = si.find("SafetyTagMap")
            safety_info = SafetyInfo(
                safety_locked=_bool_attr(si, "SafetyLocked"),
                signature_run_mode_protect=_bool_attr(si, "SignatureRunModeProtect"),
                configure_safety_io_always=_bool_attr(si, "ConfigureSafetyIOAlways"),
                safety_level=_attr(si, "SafetyLevel"),
                safety_tag_map=stm.text.strip() if stm is not None and stm.text else None,
                safety_signature=_attr(si, "SafetySignature"),
                safety_lock_password_fingerprint=_password_fingerprint(
                    _attr(si, "SafetyLockPassword")
                ),
                safety_unlock_password_fingerprint=_password_fingerprint(
                    _attr(si, "SafetyUnlockPassword")
                ),
            )

        # RedundancyInfo
        redundancy_info = None
        ri = el.find("RedundancyInfo")
        if ri is not None:
            redundancy_info = RedundancyInfo(
                enabled=_bool_attr(ri, "Enabled"),
                keep_test_edits_on_switch_over=_bool_attr(ri, "KeepTestEditsOnSwitchOver"),
            )

        # Security
        security = None
        sec = el.find("Security")
        if sec is not None:
            security = Security(
                code=_int_attr(sec, "Code", 0),
                changes_to_detect=_attr(sec, "ChangesToDetect"),
            )

        # TimeSynchronize
        time_synchronize = None
        ts = el.find("TimeSynchronize")
        if ts is not None:
            time_synchronize = TimeSynchronize(
                priority1=_int_attr(ts, "Priority1"),
                priority2=_int_attr(ts, "Priority2"),
                ptp_enable=_bool_attr(ts, "PTPEnable"),
            )

        # CST (Coordinated System Time)
        cst = None
        cst_el = el.find("CST")
        if cst_el is not None:
            cst = CST(master_id=_int_attr(cst_el, "MasterID"))

        # WallClockTime
        wall_clock_time = None
        wct = el.find("WallClockTime")
        if wct is not None:
            wall_clock_time = WallClockTime(
                local_time_adjustment=_int_attr(wct, "LocalTimeAdjustment"),
                time_zone=_int_attr(wct, "TimeZone"),
            )

        # EthernetPorts (controller's onboard ports)
        ethernet_ports: list[EthernetPort] = []
        ep_container = el.find("EthernetPorts")
        if ep_container is not None:
            for p in ep_container.findall("EthernetPort"):
                ethernet_ports.append(
                    EthernetPort(
                        port=_int_attr(p, "Port"),
                        label=_attr(p, "Label") or None,
                        port_enabled=_bool_attr(p, "PortEnabled"),
                    )
                )

        return Controller(
            name=_attr(el, "Name", ""),
            processor_type=_attr(el, "ProcessorType"),
            major_rev=_int_attr(el, "MajorRev"),
            minor_rev=_int_attr(el, "MinorRev"),
            time_slice=_int_attr(el, "TimeSlice"),
            project_creation_date=_attr(el, "ProjectCreationDate"),
            last_modified_date=_attr(el, "LastModifiedDate"),
            comm_path=_attr(el, "CommPath"),
            project_sn=_attr(el, "ProjectSN"),
            match_project_to_controller=_bool_attr(el, "MatchProjectToController"),
            can_use_rpi_from_producer=_bool_attr(el, "CanUseRPIFromProducer"),
            inhibit_automatic_firmware_update=_int_attr(el, "InhibitAutomaticFirmwareUpdate", 0),
            pass_through_configuration=_attr(el, "PassThroughConfiguration"),
            download_project_documentation_and_extended_properties=_bool_attr(
                el, "DownloadProjectDocumentationAndExtendedProperties"
            ),
            download_project_custom_properties=_bool_attr(el, "DownloadProjectCustomProperties"),
            report_minor_overflow=_bool_attr(el, "ReportMinorOverflow"),
            auto_diags_enabled=_bool_attr(el, "AutoDiagsEnabled"),
            web_server_enabled=_bool_attr(el, "WebServerEnabled"),
            power_loss_program=_attr(el, "PowerLossProgram"),
            fault_handler_program=_attr(el, "MajorFaultProgram"),
            ignore_array_faults_during_postscan=_bool_attr(
                el, "IgnoreArrayFaultsDuringPostScan"
            ),
            sfc_execution_control=_attr(el, "SFCExecutionControl"),
            sfc_last_scan=_attr(el, "SFCLastScan"),
            sfc_restart_position=_attr(el, "SFCRestartPosition"),
            description=_description(el),
            safety_info=safety_info,
            redundancy_info=redundancy_info,
            security=security,
            time_synchronize=time_synchronize,
            cst=cst,
            wall_clock_time=wall_clock_time,
            ethernet_ports=ethernet_ports,
        )

    # ------------------------------------------------------------------
    # Modules
    # ------------------------------------------------------------------

    def _parse_modules(self, controller_el: Element) -> list[Module]:
        container = controller_el.find("Modules")
        if container is None:
            return []
        return [self._parse_module(m) for m in container.findall("Module")]

    def _parse_module(self, el: Element) -> Module:
        ekey_el = el.find("EKey")
        ekey_state = _attr(ekey_el, "State") if ekey_el is not None else None

        ports: list[ModulePort] = []
        ports_el = el.find("Ports")
        if ports_el is not None:
            for p in ports_el.findall("Port"):
                bus_el = p.find("Bus")
                bus_size = _int_attr(bus_el, "Size") if bus_el is not None else None
                ports.append(
                    ModulePort(
                        id=_int_attr(p, "Id", 0),
                        type=_attr(p, "Type"),
                        address=_attr(p, "Address") or None,
                        upstream=_bool_attr(p, "Upstream"),
                        safety_network=_attr(p, "SafetyNetwork"),
                        bus_size=bus_size,
                        width=_int_attr(p, "Width"),
                    )
                )

        (
            comm_method,
            config_values,
            config_l5k,
            config_script_l5k,
            safety_script_l5k,
            connections,
            rack_connections,
        ) = self._parse_module_communications(el)

        extended_properties: dict[str, str] = {}
        ext_el = el.find("ExtendedProperties")
        if ext_el is not None:
            _flatten_xml(ext_el, "", extended_properties)

        return Module(
            name=_attr(el, "Name", ""),
            catalog_number=_attr(el, "CatalogNumber"),
            vendor=_int_attr(el, "Vendor"),
            product_type=_int_attr(el, "ProductType"),
            product_code=_int_attr(el, "ProductCode"),
            major=_int_attr(el, "Major"),
            minor=_int_attr(el, "Minor"),
            parent_module=_attr(el, "ParentModule"),
            parent_mod_port_id=_int_attr(el, "ParentModPortId"),
            inhibited=_bool_attr(el, "Inhibited"),
            major_fault=_bool_attr(el, "MajorFault"),
            safety_network=_attr(el, "SafetyNetwork"),
            safety_enabled=_opt_bool_attr(el, "SafetyEnabled"),
            auto_diags_enabled=_opt_bool_attr(el, "AutoDiagsEnabled"),
            user_defined_vendor=_int_attr(el, "UserDefinedVendor"),
            user_defined_product_type=_int_attr(el, "UserDefinedProductType"),
            user_defined_product_code=_int_attr(el, "UserDefinedProductCode"),
            user_defined_major=_int_attr(el, "UserDefinedMajor"),
            user_defined_minor=_int_attr(el, "UserDefinedMinor"),
            ekey_state=ekey_state,
            ports=ports,
            comm_method=comm_method,
            config_values=config_values,
            config_l5k=config_l5k,
            config_script_l5k=config_script_l5k,
            safety_script_l5k=safety_script_l5k,
            connections=connections,
            rack_connections=rack_connections,
            extended_properties=extended_properties,
        )

    def _parse_module_communications(
        self, module_el: Element
    ) -> tuple[
        Optional[str],
        dict[str, str],
        Optional[str],
        Optional[str],
        Optional[str],
        list[ModuleConnection],
        list[RackConnection],
    ]:
        """
        Decode the <Communications> block of a module.

        Returns ``(comm_method, config_values, config_l5k, config_script_l5k,
        safety_script_l5k, connections, rack_connections)``:
          - ``config_values`` is the flat path->value map from a decorated
            <ConfigTag>; ``config_l5k`` is the raw <ConfigData> L5K blob kept as
            a diff-detectable fallback when no decorated config tag exists.
          - ``config_script_l5k`` / ``safety_script_l5k`` are the opaque L5K text
            of any <ConfigScript> / <SafetyScript> blocks, kept verbatim.
          - <InputTag>/<OutputTag> blocks hold live I/O state (fault bits,
            receive buffers), not configuration, so their values are
            intentionally not decoded here; only their per-operand comments are.
          - ``rack_connections`` holds the alias-tag comments from any
            <RackConnection> blocks (rack-optimized connections carry no tunable
            attributes here).
        """
        comm_el = module_el.find("Communications")
        if comm_el is None:
            return None, {}, None, None, None, [], []

        comm_method = _attr(comm_el, "CommMethod")

        config_script_el = comm_el.find("ConfigScript")
        config_script_l5k = (
            _child_text(config_script_el, "Data")
            if config_script_el is not None
            else None
        )
        safety_script_el = comm_el.find("SafetyScript")
        safety_script_l5k = (
            _child_text(safety_script_el, "Data")
            if safety_script_el is not None
            else None
        )

        config_values: dict[str, str] = {}
        config_l5k: Optional[str] = None
        config_tag = comm_el.find("ConfigTag")
        if config_tag is not None:
            _, config_values = self._extract_values(config_tag, "Data")
        if not config_values:
            config_data = comm_el.find("ConfigData")
            if config_data is not None:
                scalar, _ = self._extract_values(config_data, "Data")
                config_l5k = scalar

        connections: list[ModuleConnection] = []
        connections_el = comm_el.find("Connections")
        if connections_el is not None:
            for c in connections_el.findall("Connection"):
                connections.append(
                    ModuleConnection(
                        name=_attr(c, "Name") or None,
                        rpi=_int_attr(c, "RPI"),
                        type=_attr(c, "Type"),
                        input_size=_int_attr(c, "InputSize"),
                        output_size=_int_attr(c, "OutputSize"),
                        input_cxn_point=_int_attr(c, "InputCxnPoint"),
                        output_cxn_point=_int_attr(c, "OutputCxnPoint"),
                        priority=_attr(c, "Priority"),
                        input_connection_type=_attr(c, "InputConnectionType"),
                        input_production_trigger=_attr(c, "InputProductionTrigger"),
                        unicast=_opt_bool_attr(c, "Unicast"),
                        event_id=_int_attr(c, "EventID"),
                        programmatically_send_event_trigger=_bool_attr(
                            c, "ProgrammaticallySendEventTrigger"
                        ),
                        connection_path=_attr(c, "ConnectionPath") or None,
                        input_tag_suffix=_attr(c, "InputTagSuffix") or None,
                        output_tag_suffix=_attr(c, "OutputTagSuffix") or None,
                        timeout_multiplier=_int_attr(c, "TimeoutMultiplier"),
                        network_delay_multiplier=_int_attr(c, "NetworkDelayMultiplier"),
                        reaction_time_limit=_float_attr(c, "ReactionTimeLimit"),
                        max_observed_network_delay=_float_attr(
                            c, "MaxObservedNetworkDelay"
                        ),
                        input_comments=_operand_comments(c.find("InputTag")),
                        output_comments=_operand_comments(c.find("OutputTag")),
                    )
                )

        rack_connections: list[RackConnection] = []
        if connections_el is not None:
            for rc in connections_el.findall("RackConnection"):
                in_comments = _operand_comments(rc.find("InAliasTag"))
                out_comments = _operand_comments(rc.find("OutAliasTag"))
                # A rack connection carries no other diffable data; skip it
                # entirely when neither alias tag has comments to avoid noise.
                if in_comments or out_comments:
                    rack_connections.append(
                        RackConnection(
                            in_alias_comments=in_comments,
                            out_alias_comments=out_comments,
                        )
                    )

        return (
            comm_method,
            config_values,
            config_l5k,
            config_script_l5k,
            safety_script_l5k,
            connections,
            rack_connections,
        )

    # ------------------------------------------------------------------
    # Data Types (UDTs)
    # ------------------------------------------------------------------

    def _parse_data_types(self, controller_el: Element) -> list[DataType]:
        container = controller_el.find("DataTypes")
        if container is None:
            return []
        return [self._parse_data_type(dt) for dt in container.findall("DataType")]

    def _parse_data_type(self, el: Element) -> DataType:
        members: list[UDTMember] = []
        members_el = el.find("Members")
        if members_el is not None:
            for m in members_el.findall("Member"):
                members.append(
                    UDTMember(
                        name=_attr(m, "Name", ""),
                        data_type=_attr(m, "DataType", ""),
                        dimension=_int_attr(m, "Dimension", 0),
                        radix=_attr(m, "Radix"),
                        hidden=_bool_attr(m, "Hidden"),
                        external_access=_attr(m, "ExternalAccess"),
                        description=_description(m),
                        target=_attr(m, "Target"),
                        bit_number=_int_attr(m, "BitNumber"),
                    )
                )
        return DataType(
            name=_attr(el, "Name", ""),
            family=_attr(el, "Family"),
            udt_class=_attr(el, "Class"),
            description=_description(el),
            members=members,
        )

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    def _parse_tags(self, parent_el: Element, scope: str) -> list[Tag]:
        container = parent_el.find("Tags")
        if container is None:
            return []
        return [self._parse_tag(t, scope) for t in container.findall("Tag")]

    def _extract_values(
        self, parent_el: Element, data_tag: str
    ) -> tuple[Optional[str], dict[str, str]]:
        """
        Decode the value(s) from a tag/parameter's data blocks.

        `data_tag` is the child element name to scan ("Data" for tags,
        "DefaultData" for AOI parameter/local-tag defaults).

        Returns ``(scalar_value, values_map)``:
          - a plain scalar/string value goes in ``scalar_value`` (map empty);
          - a structured/array value goes in ``values_map`` (scalar None).
        Prefers the Decorated block; falls back to String, then the raw L5K
        text if Decorated data was not exported.
        """
        decorated = string_block = l5k_block = None
        for d in parent_el.findall(data_tag):
            fmt = d.get("Format")
            if fmt == "Decorated":
                decorated = d
            elif fmt == "String":
                string_block = d
            elif fmt == "L5K":
                l5k_block = d

        if decorated is not None:
            children = list(decorated)
            if children:
                flat: dict[str, str] = {}
                _flatten_decorated(children[0], "", flat)
                if list(flat.keys()) == [_ROOT_VALUE_KEY]:
                    return flat[_ROOT_VALUE_KEY], {}
                return None, flat

        if string_block is not None and string_block.text:
            return string_block.text.strip().strip("'"), {}

        if l5k_block is not None and l5k_block.text:
            return l5k_block.text.strip(), {}

        return None, {}

    def _extract_param_block(
        self, tag_el: Element, formats: tuple[str, ...]
    ) -> dict[str, str]:
        """
        Read the parameter block from a tag's <Data Format=...> element whose
        Format is one of `formats`. These blocks (AxisParameters /
        MotionGroupParameters / MessageParameters) all share one shape: every
        parameter is an attribute on a single child element, so we take that
        element's attributes verbatim. Keyed on Format (not the child name) so
        every axis subtype is covered. Empty when no matching block exists.
        """
        for data_el in tag_el.findall("Data"):
            if data_el.get("Format") in formats:
                child = next(iter(data_el), None)
                if child is not None:
                    return dict(child.attrib)
        return {}

    def _parse_tag(self, el: Element, scope: str) -> Tag:
        tag_type = _attr(el, "TagType")
        data_type = _attr(el, "DataType", "")
        value, values = self._extract_values(el, "Data")
        return Tag(
            name=_attr(el, "Name", ""),
            scope=scope,
            tag_type=tag_type,
            alias_for=_attr(el, "AliasFor"),
            usage=_attr(el, "Usage"),
            data_type=data_type,
            dimensions=_parse_dimensions(_attr(el, "Dimensions")),
            radix=_attr(el, "Radix"),
            constant=_bool_attr(el, "Constant"),
            external_access=_attr(el, "ExternalAccess"),
            description=_description(el),
            value=value,
            values=values,
            motion_config=self._extract_param_block(el, ("Axis", "MotionGroup")),
            message_config=self._extract_param_block(el, ("Message",)),
            comments=_operand_comments(el),
            tag_class=_attr(el, "Class"),
            produced_connection=self._parse_produced_connection(el)
            if tag_type == "Produced"
            else None,
            consumed_connection=self._parse_consumed_connection(el)
            if tag_type == "Consumed"
            else None,
        )

    def _parse_produced_connection(self, tag_el: Element) -> Optional[ProducedTagConnection]:
        pi = tag_el.find("ProduceInfo")
        if pi is None:
            return None
        return ProducedTagConnection(
            produce_count=_int_attr(pi, "ProduceCount"),
            programmatically_send_event_trigger=_bool_attr(
                pi, "ProgrammaticallySendEventTrigger"
            ),
            unicast_permitted=_bool_attr(pi, "UnicastPermitted"),
            min_rpi=_float_attr(pi, "MinimumRPI"),
            max_rpi=_float_attr(pi, "MaximumRPI"),
            default_rpi=_float_attr(pi, "DefaultRPI"),
        )

    def _parse_consumed_connection(self, tag_el: Element) -> Optional[ConsumedTagConnection]:
        ci = tag_el.find("ConsumeInfo")
        if ci is None:
            return None
        unicast_raw = _attr(ci, "Unicast")
        unicast: Optional[bool] = (
            unicast_raw.strip().lower() == "true" if unicast_raw is not None else None
        )
        return ConsumedTagConnection(
            producer=_attr(ci, "Producer") or None,
            remote_tag=_attr(ci, "RemoteTag") or None,
            remote_instance=_int_attr(ci, "RemoteInstance"),
            rpi=_float_attr(ci, "RPI"),
            unicast=unicast,
            timeout_multiplier=_int_attr(ci, "TimeoutMultiplier"),
            network_delay_multiplier=_int_attr(ci, "NetworkDelayMultiplier"),
            reaction_time_limit=_float_attr(ci, "ReactionTimeLimit"),
            max_observed_network_delay=_float_attr(ci, "MaxObservedNetworkDelay"),
        )

    # ------------------------------------------------------------------
    # Add-On Instructions (AOIs)
    # ------------------------------------------------------------------

    def _parse_aois(self, controller_el: Element) -> list[AOI]:
        container = controller_el.find("AddOnInstructionDefinitions")
        if container is None:
            return []
        aois: list[AOI] = []
        for child in container:
            if child.tag == "AddOnInstructionDefinition":
                aois.append(self._parse_aoi(child))
            elif (
                child.tag == "EncodedData"
                and child.get("EncodedType") == "AddOnInstructionDefinition"
            ):
                aois.append(self._parse_encoded_aoi(child))
        return aois

    def _parse_aoi_parameters(self, el: Element) -> list[AOIParameter]:
        """Parse an AOI's <Parameters>. Shared by plain and encoded AOIs (an
        encoded AOI still exports its parameters in clear text)."""
        params: list[AOIParameter] = []
        params_el = el.find("Parameters")
        if params_el is not None:
            for p in params_el.findall("Parameter"):
                default_value, default_values = self._extract_values(p, "DefaultData")
                params.append(
                    AOIParameter(
                        name=_attr(p, "Name", ""),
                        tag_type=_attr(p, "TagType"),
                        data_type=_attr(p, "DataType", ""),
                        usage=_attr(p, "Usage"),
                        radix=_attr(p, "Radix"),
                        required=_bool_attr(p, "Required"),
                        visible=_bool_attr(p, "Visible", True),
                        external_access=_attr(p, "ExternalAccess"),
                        description=_description(p),
                        alias_for=_attr(p, "AliasFor"),
                        default_value=default_value,
                        default_values=default_values,
                        comments=_operand_comments(p),
                    )
                )
        return params

    def _parse_aoi_local_tags(self, el: Element) -> list[AOILocalTag]:
        """Parse an AOI's <LocalTags>. Empty for encoded AOIs (their local tags
        live inside the encrypted implementation blob)."""
        local_tags: list[AOILocalTag] = []
        local_tags_el = el.find("LocalTags")
        if local_tags_el is not None:
            for lt in local_tags_el.findall("LocalTag"):
                default_value, default_values = self._extract_values(lt, "DefaultData")
                local_tags.append(
                    AOILocalTag(
                        name=_attr(lt, "Name", ""),
                        data_type=_attr(lt, "DataType", ""),
                        dimensions=_parse_dimensions(_attr(lt, "Dimensions")),
                        radix=_attr(lt, "Radix"),
                        external_access=_attr(lt, "ExternalAccess"),
                        description=_description(lt),
                        default_value=default_value,
                        default_values=default_values,
                        comments=_operand_comments(lt),
                    )
                )
        return local_tags

    def _parse_encoded_aoi(self, el: Element) -> AOI:
        """Parse a source-protected AOI (<EncodedData
        EncodedType="AddOnInstructionDefinition">). The clear-text public
        interface is parsed exactly like a plain AOI; the encrypted
        implementation blob is intentionally ignored (it re-randomises every
        export), and SignatureID is captured as the change fingerprint."""
        return AOI(
            name=_attr(el, "Name", ""),
            aoi_class=_attr(el, "Class"),
            revision=_attr(el, "Revision"),
            revision_extension=_attr(el, "RevisionExtension"),
            vendor=_attr(el, "Vendor"),
            edited_date=_attr(el, "EditedDate"),
            software_revision=_attr(el, "SoftwareRevision"),
            description=_description(el),
            revision_note=_child_text(el, "RevisionNote"),
            additional_help_text=_child_text(el, "AdditionalHelpText"),
            parameters=self._parse_aoi_parameters(el),
            local_tags=self._parse_aoi_local_tags(el),
            routines=self._parse_routines(el),
            encoded=True,
            signature_id=_attr(el, "SignatureID"),
            signature_timestamp=_attr(el, "SignatureTimestamp"),
            encryption_config=_attr(el, "EncryptionConfig"),
        )

    def _parse_aoi(self, el: Element) -> AOI:
        params = self._parse_aoi_parameters(el)
        local_tags = self._parse_aoi_local_tags(el)

        return AOI(
            name=_attr(el, "Name", ""),
            aoi_class=_attr(el, "Class"),
            revision=_attr(el, "Revision"),
            revision_extension=_attr(el, "RevisionExtension"),
            vendor=_attr(el, "Vendor"),
            execute_prescan=_bool_attr(el, "ExecutePrescan"),
            execute_postscan=_bool_attr(el, "ExecutePostscan"),
            execute_enable_in_false=_bool_attr(el, "ExecuteEnableInFalse"),
            created_date=_attr(el, "CreatedDate"),
            created_by=_attr(el, "CreatedBy"),
            edited_date=_attr(el, "EditedDate"),
            edited_by=_attr(el, "EditedBy"),
            software_revision=_attr(el, "SoftwareRevision"),
            description=_description(el),
            revision_note=_child_text(el, "RevisionNote"),
            additional_help_text=_child_text(el, "AdditionalHelpText"),
            parameters=params,
            local_tags=local_tags,
            routines=self._parse_routines(el),
        )

    # ------------------------------------------------------------------
    # Programs
    # ------------------------------------------------------------------

    def _parse_programs(self, controller_el: Element) -> list[Program]:
        container = controller_el.find("Programs")
        if container is None:
            return []
        return [self._parse_program(p) for p in container.findall("Program")]

    def _parse_program(self, el: Element) -> Program:
        name = _attr(el, "Name", "")
        return Program(
            name=name,
            description=_description(el),
            test_edits=_bool_attr(el, "TestEdits"),
            main_routine_name=_attr(el, "MainRoutineName"),
            fault_routine_name=_attr(el, "FaultRoutineName"),
            disabled=_bool_attr(el, "Disabled"),
            use_as_folder=_bool_attr(el, "UseAsFolder"),
            program_class=_attr(el, "Class"),
            tags=self._parse_tags(el, scope=name),
            routines=self._parse_routines(el),
        )

    # ------------------------------------------------------------------
    # Routines
    # ------------------------------------------------------------------

    def _parse_routines(self, parent_el: Element) -> list[Routine]:
        container = parent_el.find("Routines")
        if container is None:
            return []
        routines: list[Routine] = []
        for child in container:
            if child.tag == "Routine":
                routines.append(self._parse_routine(child))
            elif child.tag == "EncodedData" and child.get("EncodedType") == "Routine":
                routines.append(self._parse_encoded_routine(child))
        return routines

    def _parse_encoded_routine(self, el: Element) -> Routine:
        """Parse a source-protected routine (<EncodedData
        EncodedType="Routine">). Only the stable metadata is captured; the
        encrypted blob is ignored (it re-randomises every export and no
        signature is emitted at routine level, so logic changes are not
        detectable). `content` is left empty."""
        return Routine(
            name=_attr(el, "Name", ""),
            type=_attr(el, "Type", "RLL"),
            content=RoutineContent(),
            encoded=True,
            encryption_config=_attr(el, "EncryptionConfig"),
        )

    def _parse_routine(self, el: Element) -> Routine:
        routine_type = _attr(el, "Type", "RLL")
        return Routine(
            name=_attr(el, "Name", ""),
            type=routine_type,
            description=_description(el),
            content=self._parse_routine_content(el, routine_type),
        )

    def _parse_routine_content(self, el: Element, routine_type: str) -> RoutineContent:
        if routine_type == "RLL":
            rll_el = el.find("RLLContent")
            if rll_el is not None:
                rungs = [
                    Rung(
                        number=_int_attr(r, "Number", 0),
                        type=_attr(r, "Type"),
                        comment=r.findtext("Comment"),
                        text=r.findtext("Text"),
                    )
                    for r in rll_el.findall("Rung")
                ]
                return RoutineContent(rungs=rungs)

        elif routine_type == "ST":
            st_el = el.find("STContent")
            if st_el is not None:
                lines = [
                    STLine(
                        number=_int_attr(line, "Number", 0),
                        level=_int_attr(line, "Level", 0),
                        # Text may be in a <Text> child element (older exports)
                        # or directly as the element's text node (newer exports)
                        text=line.findtext("Text") or (line.text or ""),
                    )
                    for line in st_el.findall("Line")
                ]
                return RoutineContent(lines=lines)

        else:
            # FBD, SFC — preserve the raw XML for future dedicated parsers
            content_el = el.find(f"{routine_type}Content")
            if content_el is not None:
                return RoutineContent(
                    raw_xml=ET.tostring(content_el, encoding="unicode")
                )

        return RoutineContent()

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    def _parse_tasks(self, controller_el: Element) -> list[Task]:
        container = controller_el.find("Tasks")
        if container is None:
            return []
        return [self._parse_task(t) for t in container.findall("Task")]

    def _parse_task(self, el: Element) -> Task:
        scheduled: list[str] = []
        sp_container = el.find("ScheduledPrograms")
        if sp_container is not None:
            scheduled = [
                _attr(sp, "Name", "")
                for sp in sp_container.findall("ScheduledProgram")
            ]
        task_type = _attr(el, "Type", "CONTINUOUS")
        return Task(
            name=_attr(el, "Name", ""),
            type=task_type,
            rate=_float_attr(el, "Rate"),
            priority=_int_attr(el, "Priority"),
            watchdog=_float_attr(el, "Watchdog"),
            disable_update_outputs=_bool_attr(el, "DisableUpdateOutputs"),
            inhibit_task=_bool_attr(el, "InhibitTask"),
            task_class=_attr(el, "Class"),
            scheduled_programs=scheduled,
            event_info=self._parse_event_info(el) if task_type == "EVENT" else None,
        )

    def _parse_event_info(self, task_el: Element) -> Optional[EventInfo]:
        ei = task_el.find("EventInfo")
        if ei is None:
            return None
        return EventInfo(
            event_type=_attr(ei, "EventType"),
            event_tag=_attr(ei, "EventTag") or None,
            module_name=_attr(ei, "ModuleName") or None,
            module_input_specifier=_attr(ei, "ModuleSpecifier") or None,
            timeout=_float_attr(ei, "Timeout"),
            event_on_reset=_bool_attr(ei, "EventOnReset"),
        )
