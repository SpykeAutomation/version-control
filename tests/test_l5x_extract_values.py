"""Tests for L5XParser._extract_values and ._extract_param_block.

A tag can carry its value in up to three formats. _extract_values must
prefer Decorated, then fall back to String, then to raw L5K text — these
tests pin that order and the scalar-vs-structure split of the result.
"""
import xml.etree.ElementTree as ET


def extract(l5x, inner: str, data_tag: str = "Data"):
    el = ET.fromstring(f"<Tag>{inner}</Tag>")
    return l5x._extract_values(el, data_tag)


DECORATED_SCALAR = '<Data Format="Decorated"><DataValue DataType="DINT" Value="5"/></Data>'
DECORATED_STRUCT = (
    '<Data Format="Decorated">'
    '<Structure DataType="DemoUDT"><DataValueMember Name="Mode" Value="2"/></Structure>'
    "</Data>"
)
STRING_BLOCK = "<Data Format=\"String\">'hello'</Data>"
L5K_BLOCK = '<Data Format="L5K">[1,2,3]</Data>'


def test_decorated_root_scalar(l5x):
    value, values = extract(l5x, DECORATED_SCALAR)
    assert value == "5"
    assert values == {}


def test_decorated_structure(l5x):
    value, values = extract(l5x, DECORATED_STRUCT)
    assert value is None
    assert values == {"Mode": "2"}


def test_decorated_wins_over_string_and_l5k(l5x):
    value, values = extract(l5x, L5K_BLOCK + STRING_BLOCK + DECORATED_SCALAR)
    assert value == "5"
    assert values == {}


def test_string_wins_over_l5k(l5x):
    value, values = extract(l5x, L5K_BLOCK + STRING_BLOCK)
    assert value == "hello"
    assert values == {}


def test_l5k_fallback_keeps_raw_text(l5x):
    value, values = extract(l5x, L5K_BLOCK)
    assert value == "[1,2,3]"
    assert values == {}


def test_no_data_children(l5x):
    assert extract(l5x, "") == (None, {})


def test_empty_decorated_block_falls_through_to_string(l5x):
    value, _ = extract(l5x, '<Data Format="Decorated"/>' + STRING_BLOCK)
    assert value == "hello"


def test_data_tag_name_is_honored(l5x):
    inner = (
        '<DefaultData Format="Decorated"><DataValue DataType="DINT" Value="9"/></DefaultData>'
        + DECORATED_SCALAR
    )
    value, _ = extract(l5x, inner, data_tag="DefaultData")
    assert value == "9"


def test_string_fallback_strips_all_outer_quotes(l5x):
    # Documents current behavior: .strip("'") removes every leading/trailing
    # quote, unlike _clean_ascii_string which removes exactly one pair
    # (REMAINING_ISSUES 5). Update this if that cleanup lands.
    value, _ = extract(l5x, "<Data Format=\"String\">''quoted''</Data>")
    assert value == "quoted"


def test_extract_param_block_matches_format(l5x):
    el = ET.fromstring(
        '<Tag><Data Format="Axis"><AxisParams CtrlMode="Position" Gain="2"/></Data></Tag>'
    )
    assert l5x._extract_param_block(el, ("Axis", "MotionGroup")) == {
        "CtrlMode": "Position",
        "Gain": "2",
    }


def test_extract_param_block_ignores_other_formats(l5x):
    el = ET.fromstring(f"<Tag>{DECORATED_SCALAR}</Tag>")
    assert l5x._extract_param_block(el, ("Message",)) == {}
