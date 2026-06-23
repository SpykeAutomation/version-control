"""End-to-end tests for tag parsing (controller- and program-scoped)."""
import pytest

from fixtures_l5x import make_l5x


def parse_tag(l5x, tag_xml: str):
    doc = l5x.parse_string(make_l5x(body=f"<Tags>{tag_xml}</Tags>"))
    assert len(doc.controller_tags) == 1
    return doc.controller_tags[0]


def test_base_scalar_tag(l5x):
    tag = parse_tag(
        l5x,
        '<Tag Name="CycleCount" TagType="Base" DataType="DINT" Radix="Decimal">'
        '<Data Format="Decorated"><DataValue DataType="DINT" Radix="Decimal" Value="5"/></Data>'
        "</Tag>",
    )
    assert tag.name == "CycleCount"
    assert tag.scope == "controller"
    assert tag.tag_type == "Base"
    assert tag.data_type == "DINT"
    assert tag.radix == "Decimal"
    assert tag.value == "5"
    assert tag.values == {}
    assert tag.dimensions is None


def test_structured_tag_gets_flat_value_map(l5x):
    tag = parse_tag(
        l5x,
        '<Tag Name="MixerState" TagType="Base" DataType="DemoUDT">'
        '<Data Format="Decorated">'
        '<Structure DataType="DemoUDT">'
        '<DataValueMember Name="Mode" DataType="DINT" Value="2"/>'
        '<DataValueMember Name="Run" DataType="BOOL" Value="1"/>'
        "</Structure></Data></Tag>",
    )
    assert tag.value is None
    assert tag.values == {"Mode": "2", "Run": "1"}


@pytest.mark.parametrize(
    ("dims_attr", "expected"),
    [("4", [4]), ("4 2", [4, 2])],
)
def test_array_tag_dimensions(l5x, dims_attr, expected):
    tag = parse_tag(
        l5x,
        f'<Tag Name="Totals" TagType="Base" DataType="DINT" Dimensions="{dims_attr}"/>',
    )
    assert tag.dimensions == expected


def test_array_tag_values_use_index_keys(l5x):
    tag = parse_tag(
        l5x,
        '<Tag Name="Totals" TagType="Base" DataType="DINT" Dimensions="2">'
        '<Data Format="Decorated">'
        '<Array DataType="DINT" Dimensions="2">'
        '<Element Index="[0]" Value="7"/>'
        '<Element Index="[1]" Value="8"/>'
        "</Array></Data></Tag>",
    )
    assert tag.values == {"[0]": "7", "[1]": "8"}


def test_alias_tag(l5x):
    tag = parse_tag(
        l5x,
        '<Tag Name="StartPB" TagType="Alias" AliasFor="LocalIn.3" Radix="Decimal"/>',
    )
    assert tag.tag_type == "Alias"
    assert tag.alias_for == "LocalIn.3"


def test_produced_tag_connection(l5x):
    tag = parse_tag(
        l5x,
        '<Tag Name="LineStatus" TagType="Produced" DataType="DINT">'
        '<ProduceInfo ProduceCount="2" UnicastPermitted="true"'
        ' MinimumRPI="0.196" MaximumRPI="536870.875" DefaultRPI="20.0"/>'
        "</Tag>",
    )
    pc = tag.produced_connection
    assert pc.produce_count == 2
    assert pc.unicast_permitted is True
    assert pc.min_rpi == 0.196
    assert pc.max_rpi == 536870.875
    assert pc.default_rpi == 20.0


@pytest.mark.parametrize(
    ("unicast_attr", "expected"),
    [("", None), (' Unicast="true"', True), (' Unicast="false"', False)],
)
def test_consumed_tag_connection_unicast_tri_state(l5x, unicast_attr, expected):
    tag = parse_tag(
        l5x,
        f'<Tag Name="PeerStatus" TagType="Consumed" DataType="DINT">'
        f'<ConsumeInfo Producer="PeerCtrl" RemoteTag="LineStatus" RPI="20.0"{unicast_attr}/>'
        f"</Tag>",
    )
    cc = tag.consumed_connection
    assert cc.producer == "PeerCtrl"
    assert cc.remote_tag == "LineStatus"
    assert cc.rpi == 20.0
    assert cc.unicast is expected


def test_string_format_fallback(l5x):
    tag = parse_tag(
        l5x,
        '<Tag Name="LineName" TagType="Base" DataType="STRING">'
        "<Data Format=\"String\">'mixer'</Data></Tag>",
    )
    assert tag.value == "mixer"


def test_l5k_only_fallback(l5x):
    tag = parse_tag(
        l5x,
        '<Tag Name="RawCfg" TagType="Base" DataType="DINT" Dimensions="2">'
        '<Data Format="L5K">[1,2]</Data></Tag>',
    )
    assert tag.value == "[1,2]"
    assert tag.values == {}


def test_operand_comments(l5x):
    tag = parse_tag(
        l5x,
        '<Tag Name="StatusWord" TagType="Base" DataType="DINT">'
        "<Comments>"
        '<Comment Operand=".0">running</Comment>'
        '<Comment Operand=".1">faulted</Comment>'
        "</Comments></Tag>",
    )
    assert tag.comments == {".0": "running", ".1": "faulted"}


def test_description_constant_and_external_access(l5x):
    tag = parse_tag(
        l5x,
        '<Tag Name="MaxTemp" TagType="Base" DataType="REAL" Constant="true"'
        ' ExternalAccess="Read Only">'
        "<Description>Upper temperature limit</Description></Tag>",
    )
    assert tag.constant is True
    assert tag.external_access == "Read Only"
    assert tag.description == "Upper temperature limit"


@pytest.mark.parametrize("fmt", ["Axis", "MotionGroup"])
def test_motion_config_captured_verbatim(l5x, fmt):
    tag = parse_tag(
        l5x,
        f'<Tag Name="Axis01" TagType="Base" DataType="AXIS_CIP_DRIVE">'
        f'<Data Format="{fmt}"><Params CtrlMode="Position" Gain="2.5"/></Data></Tag>',
    )
    assert tag.motion_config == {"CtrlMode": "Position", "Gain": "2.5"}
    assert tag.message_config == {}


def test_message_config_captured_verbatim(l5x):
    tag = parse_tag(
        l5x,
        '<Tag Name="ReadMsg" TagType="Base" DataType="MESSAGE">'
        '<Data Format="Message">'
        '<MessageParameters MessageType="CIP Data Table Read" RemoteElement="PeerTag"/>'
        "</Data></Tag>",
    )
    assert tag.message_config == {
        "MessageType": "CIP Data Table Read",
        "RemoteElement": "PeerTag",
    }
    assert tag.motion_config == {}


def test_safety_tag_class(l5x):
    tag = parse_tag(l5x, '<Tag Name="SafeStop" TagType="Base" DataType="BOOL" Class="Safety"/>')
    assert tag.tag_class == "Safety"


def test_program_scoped_tags_use_program_name_as_scope(l5x):
    doc = l5x.parse_string(
        make_l5x(
            body=(
                "<Programs>"
                '<Program Name="MixerProg">'
                '<Tags><Tag Name="StepNo" TagType="Base" DataType="DINT" Usage="Local"/></Tags>'
                "</Program>"
                "</Programs>"
            )
        )
    )
    tag = doc.programs[0].tags[0]
    assert tag.scope == "MixerProg"
    assert tag.usage == "Local"


def test_tag_custom_properties_flattened(l5x):
    tag = parse_tag(
        l5x,
        '<Tag Name="LibTag" TagType="Base" DataType="DINT">'
        "<CustomProperties><Properties><Property Name=\"VersionMaj\">2</Property>"
        "</Properties></CustomProperties></Tag>",
    )
    assert tag.custom_properties == {
        "Properties.Property.@Name": "VersionMaj",
        "Properties.Property.#text": "2",
    }
