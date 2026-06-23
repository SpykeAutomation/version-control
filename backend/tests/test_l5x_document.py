"""End-to-end tests for whole-document parsing.

Covers the document envelope and metadata, the controller's own settings
(safety, redundancy, security, time sync, Ethernet ports), and what the
parser raises when given bad or unsafe XML.
"""
import hashlib
import xml.etree.ElementTree as ET

import pytest
from defusedxml import DefusedXmlException

from fixtures_l5x import make_l5x


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_wrong_root_element_raises(l5x):
    with pytest.raises(ValueError, match="Expected root element"):
        l5x.parse_string("<NotAnL5X/>")


def test_missing_controller_raises(l5x):
    with pytest.raises(ValueError, match="No <Controller>"):
        l5x.parse_string("<RSLogix5000Content SchemaRevision='1.0'/>")


def test_malformed_xml_raises(l5x):
    with pytest.raises(ET.ParseError):
        l5x.parse_string("<RSLogix5000Content><Controller</RSLogix5000Content>")


def test_entity_declarations_are_rejected(l5x):
    malicious = (
        '<?xml version="1.0"?>'
        '<!DOCTYPE RSLogix5000Content [<!ENTITY x "boom">]>'
        "<RSLogix5000Content><Controller Name='&x;'/></RSLogix5000Content>"
    )
    with pytest.raises(DefusedXmlException):
        l5x.parse_string(malicious)


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


def test_metadata_round_trip(l5x):
    doc = l5x.parse_string(
        make_l5x(root_attrs='ExportDate="Mon Jan 05 10:00:00 2026" ExportOptions="References"')
    )
    md = doc.metadata
    assert md.schema_revision == "1.0"
    assert md.software_revision == "35.00"
    assert md.target_name == "ctrllr"
    assert md.target_type == "Controller"
    assert md.export_date == "Mon Jan 05 10:00:00 2026"
    assert md.export_options == "References"


@pytest.mark.parametrize(
    ("root_attrs", "expected"),
    [
        ("", None),
        ('ContainsContext="true"', True),
        ('ContainsContext="false"', False),
    ],
)
def test_contains_context_tri_state(l5x, root_attrs, expected):
    doc = l5x.parse_string(make_l5x(root_attrs=root_attrs))
    assert doc.metadata.contains_context is expected


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------


def test_minimal_document_has_empty_entity_lists(l5x):
    doc = l5x.parse_string(make_l5x())
    assert doc.controller.name == "ctrllr"
    assert doc.modules == []
    assert doc.data_types == []
    assert doc.add_on_instructions == []
    assert doc.controller_tags == []
    assert doc.programs == []
    assert doc.tasks == []


def test_controller_attributes_and_description(l5x):
    doc = l5x.parse_string(
        make_l5x(
            body="<Description>Main line controller</Description>",
            controller_attrs=(
                'TimeSlice="20" ProjectSN="16#0001" CommPath="AB_ETH-1\\10.0.0.1"'
                ' LastModifiedDate="Mon Jan 05 10:00:00 2026"'
                ' MajorFaultProgram="FaultHandler" PowerLossProgram="PowerUp"'
                ' MatchProjectToController="true" EtherNetIPMode="Dual-IP"'
                ' SFCExecutionControl="CurrentActive" Use="Target"'
            ),
        )
    )
    c = doc.controller
    assert c.processor_type == "1756-L85E"
    assert c.major_rev == 35
    assert c.minor_rev == 11
    assert c.time_slice == 20
    assert c.project_sn == "16#0001"
    assert c.comm_path == "AB_ETH-1\\10.0.0.1"
    assert c.last_modified_date == "Mon Jan 05 10:00:00 2026"
    assert c.fault_handler_program == "FaultHandler"
    assert c.power_loss_program == "PowerUp"
    assert c.match_project_to_controller is True
    assert c.ethernet_ip_mode == "Dual-IP"
    assert c.sfc_execution_control == "CurrentActive"
    assert c.use == "Target"
    assert c.description == "Main line controller"


def test_safety_info_with_password_fingerprints(l5x):
    lock_cipher = "QmFzZTY0Q2lwaGVyAA=="
    unlock_cipher = "T3RoZXJDaXBoZXIAAA=="
    doc = l5x.parse_string(
        make_l5x(
            body=(
                f'<SafetyInfo SafetyLocked="true" SafetyLevel="SIL2/PLd"'
                f' SafetySignature="16#abcd_1234" SignatureRunModeProtect="true"'
                f' SafetyLockPassword="{lock_cipher}"'
                f' SafetyUnlockPassword="{unlock_cipher}">'
                f"<SafetyTagMap>SafeIn=StdIn</SafetyTagMap>"
                f"</SafetyInfo>"
            )
        )
    )
    si = doc.controller.safety_info
    assert si.safety_locked is True
    assert si.signature_run_mode_protect is True
    assert si.configure_safety_io_always is False
    assert si.safety_level == "SIL2/PLd"
    assert si.safety_signature == "16#abcd_1234"
    assert si.safety_tag_map == "SafeIn=StdIn"
    expected_lock = hashlib.sha256(lock_cipher.encode("utf-8")).hexdigest()[:16]
    assert si.safety_lock_password_fingerprint == expected_lock
    assert si.safety_unlock_password_fingerprint != si.safety_lock_password_fingerprint
    # The ciphertext itself must never be persisted, only the fingerprint.
    dump = doc.model_dump_json()
    assert lock_cipher not in dump
    assert unlock_cipher not in dump


def test_redundancy_security_and_time_sync(l5x):
    doc = l5x.parse_string(
        make_l5x(
            body=(
                '<RedundancyInfo Enabled="true" KeepTestEditsOnSwitchOver="true"/>'
                '<Security Code="3" ChangesToDetect="16#ffff_ffff"/>'
                '<TimeSynchronize Priority1="128" Priority2="129" PTPEnable="true"/>'
            )
        )
    )
    c = doc.controller
    assert c.redundancy_info.enabled is True
    assert c.redundancy_info.keep_test_edits_on_switch_over is True
    assert c.security.code == 3
    assert c.security.changes_to_detect == "16#ffff_ffff"
    assert c.time_synchronize.priority1 == 128
    assert c.time_synchronize.priority2 == 129
    assert c.time_synchronize.ptp_enable is True


def test_cst_wall_clock_and_ethernet_ports(l5x):
    doc = l5x.parse_string(
        make_l5x(
            body=(
                '<CST MasterID="0"/>'
                '<WallClockTime LocalTimeAdjustment="0" TimeZone="-300"/>'
                "<EthernetPorts>"
                '<EthernetPort Port="1" Label="A1" PortEnabled="true"/>'
                '<EthernetPort Port="2" Label="A2" PortEnabled="false"/>'
                "</EthernetPorts>"
            )
        )
    )
    c = doc.controller
    assert c.cst.master_id == 0
    assert c.wall_clock_time.local_time_adjustment == 0
    assert c.wall_clock_time.time_zone == -300
    assert [(p.port, p.label, p.port_enabled) for p in c.ethernet_ports] == [
        (1, "A1", True),
        (2, "A2", False),
    ]


def test_parse_file_matches_parse_string(l5x, tmp_path):
    xml = make_l5x(body='<Tags><Tag Name="RunFlag" TagType="Base" DataType="BOOL"/></Tags>')
    path = tmp_path / "doc.xml"
    path.write_text(xml, encoding="utf-8")
    assert l5x.parse_file(str(path)).model_dump_json() == l5x.parse_string(xml).model_dump_json()
