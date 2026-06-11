"""End-to-end tests for UDT and Add-On Instruction parsing."""
from fixtures_l5x import make_l5x


def parse_udt(l5x, udt_xml: str):
    doc = l5x.parse_string(make_l5x(body=f"<DataTypes>{udt_xml}</DataTypes>"))
    assert len(doc.data_types) == 1
    return doc.data_types[0]


def parse_aois(l5x, aoi_xml: str):
    doc = l5x.parse_string(
        make_l5x(body=f"<AddOnInstructionDefinitions>{aoi_xml}</AddOnInstructionDefinitions>")
    )
    return doc.add_on_instructions


# ---------------------------------------------------------------------------
# UDTs
# ---------------------------------------------------------------------------


def test_udt_members(l5x):
    udt = parse_udt(
        l5x,
        '<DataType Name="DemoUDT" Family="NoFamily" Class="User">'
        "<Description>Demo type</Description>"
        "<Members>"
        '<Member Name="Setpoints" DataType="REAL" Dimension="4" Radix="Float"'
        ' Hidden="false" ExternalAccess="Read/Write">'
        "<Description>per-stage setpoints</Description></Member>"
        '<Member Name="ZZZZZZZZZZDemoU0" DataType="SINT" Dimension="0" Hidden="true"/>'
        "</Members></DataType>",
    )
    assert udt.name == "DemoUDT"
    assert udt.family == "NoFamily"
    assert udt.udt_class == "User"
    assert udt.description == "Demo type"
    m0, m1 = udt.members
    assert m0.name == "Setpoints"
    assert m0.data_type == "REAL"
    assert m0.dimension == 4
    assert m0.radix == "Float"
    assert m0.hidden is False
    assert m0.external_access == "Read/Write"
    assert m0.description == "per-stage setpoints"
    assert m1.hidden is True


def test_udt_bit_member_target(l5x):
    udt = parse_udt(
        l5x,
        '<DataType Name="DemoUDT">'
        "<Members>"
        '<Member Name="ZZZZZZZZZZDemoU0" DataType="SINT" Dimension="0" Hidden="true"/>'
        '<Member Name="RunFlag" DataType="BIT" Dimension="0"'
        ' Target="ZZZZZZZZZZDemoU0" BitNumber="0"/>'
        "</Members></DataType>",
    )
    bit = udt.members[1]
    assert bit.data_type == "BIT"
    assert bit.target == "ZZZZZZZZZZDemoU0"
    assert bit.bit_number == 0


def test_udt_custom_properties(l5x):
    udt = parse_udt(
        l5x,
        '<DataType Name="LibUDT">'
        '<CustomProperties><Versions><Maj>2</Maj></Versions></CustomProperties>'
        "</DataType>",
    )
    assert udt.custom_properties == {"Versions.Maj.#text": "2"}


# ---------------------------------------------------------------------------
# Plain AOIs
# ---------------------------------------------------------------------------


def test_aoi_metadata(l5x):
    (aoi,) = parse_aois(
        l5x,
        '<AddOnInstructionDefinition Name="ValveCtl" Class="Standard" Revision="3.1"'
        ' RevisionExtension="beta" Vendor="DemoVendor" ExecutePrescan="true"'
        ' ExecutePostscan="false" ExecuteEnableInFalse="true"'
        ' CreatedDate="2025-01-02T03:04:05.000Z" CreatedBy="EngA"'
        ' EditedDate="2025-02-02T03:04:05.000Z" EditedBy="EngB" SoftwareRevision="v35.00">'
        "<Description>Valve control</Description>"
        "<RevisionNote>tuned timings</RevisionNote>"
        "<AdditionalHelpText>see manual</AdditionalHelpText>"
        "</AddOnInstructionDefinition>",
    )
    assert aoi.name == "ValveCtl"
    assert aoi.aoi_class == "Standard"
    assert aoi.revision == "3.1"
    assert aoi.revision_extension == "beta"
    assert aoi.vendor == "DemoVendor"
    assert aoi.execute_prescan is True
    assert aoi.execute_postscan is False
    assert aoi.execute_enable_in_false is True
    assert aoi.created_date == "2025-01-02T03:04:05.000Z"
    assert aoi.created_by == "EngA"
    assert aoi.edited_by == "EngB"
    assert aoi.software_revision == "v35.00"
    assert aoi.description == "Valve control"
    assert aoi.revision_note == "tuned timings"
    assert aoi.additional_help_text == "see manual"
    assert aoi.encoded is False
    assert aoi.signature_id is None


def test_aoi_parameters(l5x):
    (aoi,) = parse_aois(
        l5x,
        '<AddOnInstructionDefinition Name="ValveCtl">'
        "<Parameters>"
        '<Parameter Name="OpenTime" TagType="Base" DataType="DINT" Usage="Input"'
        ' Radix="Decimal" Required="true" Visible="true" Min="0" Max="600">'
        "<Description>open travel time</Description>"
        '<DefaultData Format="Decorated"><DataValue DataType="DINT" Value="30"/></DefaultData>'
        "</Parameter>"
        '<Parameter Name="Setpoints" TagType="Base" DataType="REAL" Usage="InOut"'
        ' Dimensions="4" Constant="true"/>'
        '<Parameter Name="MirrorOut" TagType="Alias" DataType="BOOL" Usage="Output"'
        ' AliasFor="OpenTime.0"/>'
        "</Parameters>"
        "</AddOnInstructionDefinition>",
    )
    p0, p1, p2 = aoi.parameters
    assert p0.usage == "Input"
    assert p0.required is True
    assert p0.visible is True
    assert (p0.min, p0.max) == ("0", "600")
    assert p0.description == "open travel time"
    assert p0.default_value == "30"
    assert p0.default_values == {}
    assert p1.dimensions == [4]
    assert p1.constant is True
    assert p1.required is False  # absent attribute
    assert p1.visible is True  # Visible defaults to True when absent
    assert p2.alias_for == "OpenTime.0"


def test_aoi_parameter_structured_default(l5x):
    (aoi,) = parse_aois(
        l5x,
        '<AddOnInstructionDefinition Name="ValveCtl">'
        "<Parameters>"
        '<Parameter Name="Cfg" TagType="Base" DataType="DemoUDT" Usage="Input">'
        '<DefaultData Format="Decorated">'
        '<Structure DataType="DemoUDT"><DataValueMember Name="Mode" Value="1"/></Structure>'
        "</DefaultData></Parameter>"
        "</Parameters>"
        "</AddOnInstructionDefinition>",
    )
    param = aoi.parameters[0]
    assert param.default_value is None
    assert param.default_values == {"Mode": "1"}


def test_aoi_local_tags(l5x):
    (aoi,) = parse_aois(
        l5x,
        '<AddOnInstructionDefinition Name="ValveCtl">'
        "<LocalTags>"
        '<LocalTag Name="TravelTmr" DataType="TIMER" ExternalAccess="None">'
        "<Description>travel timer</Description>"
        '<Comments><Comment Operand=".DN">travel done</Comment></Comments>'
        "</LocalTag>"
        "</LocalTags>"
        "</AddOnInstructionDefinition>",
    )
    lt = aoi.local_tags[0]
    assert lt.name == "TravelTmr"
    assert lt.data_type == "TIMER"
    assert lt.external_access == "None"
    assert lt.description == "travel timer"
    assert lt.comments == {".DN": "travel done"}


def test_aoi_with_rll_routine(l5x):
    (aoi,) = parse_aois(
        l5x,
        '<AddOnInstructionDefinition Name="ValveCtl">'
        "<Routines>"
        '<Routine Name="Logic" Type="RLL">'
        '<RLLContent><Rung Number="0"><Text>NOP();</Text></Rung></RLLContent>'
        "</Routine>"
        "</Routines>"
        "</AddOnInstructionDefinition>",
    )
    routine = aoi.routines[0]
    assert routine.name == "Logic"
    assert routine.content.rungs[0].text == "NOP();"


# ---------------------------------------------------------------------------
# Encoded AOIs
# ---------------------------------------------------------------------------


ENCODED_AOI = (
    '<EncodedData EncodedType="AddOnInstructionDefinition" Name="ProtValveCtl"'
    ' Revision="2.0" Vendor="DemoVendor" EditedDate="2025-03-03T00:00:00.000Z"'
    ' SoftwareRevision="v35.00" SignatureID="16#1234_abcd"'
    ' SignatureTimestamp="2025-03-03T00:00:01.000Z" EncryptionConfig="2">'
    "<Description>Protected valve control</Description>"
    "<CustomProperties><Versions><Maj>4</Maj></Versions></CustomProperties>"
    "<Parameters>"
    '<Parameter Name="OpenTime" TagType="Base" DataType="DINT" Usage="Input" Min="0"/>'
    "</Parameters>"
    "ZW5jb2RlZC1ibG9i"
    "</EncodedData>"
)


def test_encoded_aoi(l5x):
    (aoi,) = parse_aois(l5x, ENCODED_AOI)
    assert aoi.encoded is True
    assert aoi.name == "ProtValveCtl"
    assert aoi.signature_id == "16#1234_abcd"
    assert aoi.signature_timestamp == "2025-03-03T00:00:01.000Z"
    assert aoi.encryption_config == "2"
    assert aoi.description == "Protected valve control"
    assert aoi.custom_properties == {"Versions.Maj.#text": "4"}
    # The public interface still parses; the implementation stays opaque.
    assert aoi.parameters[0].name == "OpenTime"
    assert aoi.parameters[0].min == "0"
    assert aoi.local_tags == []
    # The encrypted blob must not be persisted.
    assert "ZW5jb2RlZC1ibG9i" not in aoi.model_dump_json()


def test_plain_and_encoded_aois_keep_document_order(l5x):
    aois = parse_aois(
        l5x,
        '<AddOnInstructionDefinition Name="PlainOne"/>' + ENCODED_AOI,
    )
    assert [(a.name, a.encoded) for a in aois] == [
        ("PlainOne", False),
        ("ProtValveCtl", True),
    ]


def test_encoded_aoi_without_signature_id(l5x):
    (aoi,) = parse_aois(
        l5x,
        '<EncodedData EncodedType="AddOnInstructionDefinition" Name="NoSigAOI"'
        ' EncryptionConfig="2">blob</EncodedData>',
    )
    assert aoi.encoded is True
    assert aoi.signature_id is None  # no stable fingerprint for this AOI
