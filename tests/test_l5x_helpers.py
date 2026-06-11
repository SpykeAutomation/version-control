"""Unit tests for the helper functions in parsers/l5x/parser.py.

Covers the two flattening walks (_flatten_decorated for tag data,
_flatten_xml for free-form metadata), the attribute readers, and the
small string/dimension/password utilities. Each test builds a small XML
element directly and checks the exact dictionary the helper produces.
"""
import hashlib
import xml.etree.ElementTree as ET

import pytest

from parsers.l5x.parser import (
    _ROOT_VALUE_KEY,
    _bool_attr,
    _clean_ascii_string,
    _flatten_decorated,
    _flatten_xml,
    _float_attr,
    _int_attr,
    _opt_bool_attr,
    _parse_dimensions,
    _password_fingerprint,
)


def flatten_decorated(xml: str) -> dict[str, str]:
    out: dict[str, str] = {}
    _flatten_decorated(ET.fromstring(xml), "", out)
    return out


def flatten_xml(xml: str) -> dict[str, str]:
    out: dict[str, str] = {}
    _flatten_xml(ET.fromstring(xml), "", out)
    return out


# ---------------------------------------------------------------------------
# _parse_dimensions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10", [10]),
        ("10 5", [10, 5]),
        ("[10,5]", [10, 5]),
        ("[10, 5]", [10, 5]),
        ("0", None),
        (None, None),
        ("", None),
        ("   ", None),
        ("abc", None),
    ],
)
def test_parse_dimensions(raw, expected):
    assert _parse_dimensions(raw) == expected


# ---------------------------------------------------------------------------
# _password_fingerprint
# ---------------------------------------------------------------------------


def test_password_fingerprint_none_passthrough():
    assert _password_fingerprint(None) is None


def test_password_fingerprint_is_sha256_prefix():
    ciphertext = "AAAAQUJDREVGRw=="
    expected = hashlib.sha256(ciphertext.encode("utf-8")).hexdigest()[:16]
    fp = _password_fingerprint(ciphertext)
    assert fp == expected
    assert len(fp) == 16


def test_password_fingerprint_distinct_inputs_differ():
    assert _password_fingerprint("aaa") != _password_fingerprint("bbb")


# ---------------------------------------------------------------------------
# Attribute helpers
# ---------------------------------------------------------------------------


ATTR_EL = ET.fromstring('<E T="true" U=" TRUE " F="false" J="junk" N="7" X="x" R="1.5"/>')


def test_bool_attr():
    assert _bool_attr(ATTR_EL, "T") is True
    assert _bool_attr(ATTR_EL, "U") is True  # case/whitespace-insensitive
    assert _bool_attr(ATTR_EL, "F") is False
    assert _bool_attr(ATTR_EL, "J") is False
    assert _bool_attr(ATTR_EL, "Missing") is False
    assert _bool_attr(ATTR_EL, "Missing", default=True) is True


def test_opt_bool_attr():
    assert _opt_bool_attr(ATTR_EL, "T") is True
    assert _opt_bool_attr(ATTR_EL, "F") is False
    assert _opt_bool_attr(ATTR_EL, "Missing") is None


def test_int_attr():
    assert _int_attr(ATTR_EL, "N") == 7
    assert _int_attr(ATTR_EL, "X") is None
    assert _int_attr(ATTR_EL, "X", default=3) == 3
    assert _int_attr(ATTR_EL, "Missing") is None
    assert _int_attr(ATTR_EL, "Missing", default=0) == 0


def test_float_attr():
    assert _float_attr(ATTR_EL, "R") == 1.5
    assert _float_attr(ATTR_EL, "N") == 7.0
    assert _float_attr(ATTR_EL, "X") is None
    assert _float_attr(ATTR_EL, "Missing", default=2.0) == 2.0


# ---------------------------------------------------------------------------
# _clean_ascii_string
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("'hi'", "hi"),
        ("\n'a b'\n", "a b"),  # surrounding whitespace stripped before quotes
        ("''x''", "'x'"),  # exactly one quote pair removed
        ("'  spaced  '", "  spaced  "),  # inner spaces preserved
        ("'", "'"),  # a lone quote is not a pair
        ("plain", "plain"),
        (None, ""),
        ("", ""),
    ],
)
def test_clean_ascii_string(raw, expected):
    assert _clean_ascii_string(raw) == expected


# ---------------------------------------------------------------------------
# _flatten_decorated
# ---------------------------------------------------------------------------


def test_decorated_root_scalar():
    out = flatten_decorated('<DataValue DataType="DINT" Radix="Decimal" Value="5"/>')
    assert out == {_ROOT_VALUE_KEY: "5"}


def test_decorated_root_scalar_missing_value():
    out = flatten_decorated('<DataValue DataType="DINT"/>')
    assert out == {_ROOT_VALUE_KEY: ""}


def test_decorated_flat_structure():
    out = flatten_decorated(
        '<Structure DataType="DemoUDT">'
        '<DataValueMember Name="Mode" DataType="DINT" Value="2"/>'
        '<DataValueMember Name="Run" DataType="BOOL" Value="1"/>'
        "</Structure>"
    )
    assert out == {"Mode": "2", "Run": "1"}


def test_decorated_nested_structure_members_use_dotted_paths():
    out = flatten_decorated(
        '<Structure DataType="OuterType">'
        '<StructureMember Name="Inner" DataType="InnerType">'
        '<StructureMember Name="Deep" DataType="DeepType">'
        '<DataValueMember Name="Leaf" DataType="DINT" Value="7"/>'
        "</StructureMember>"
        "</StructureMember>"
        "</Structure>"
    )
    assert out == {"Inner.Deep.Leaf": "7"}


def test_decorated_root_string_collapses_to_text():
    out = flatten_decorated(
        '<Structure DataType="STRING">'
        '<DataValueMember Name="LEN" DataType="DINT" Value="3"/>'
        '<DataValueMember Name="DATA" DataType="SINT" Radix="ASCII">\'abc\'</DataValueMember>'
        "</Structure>"
    )
    assert out == {_ROOT_VALUE_KEY: "abc"}


def test_decorated_string_member_collapses_under_member_name():
    out = flatten_decorated(
        '<Structure DataType="DemoUDT">'
        '<StructureMember Name="Msg" DataType="STRING">'
        '<DataValueMember Name="LEN" DataType="DINT" Value="2"/>'
        '<DataValueMember Name="DATA" DataType="SINT" Radix="ASCII">\'hi\'</DataValueMember>'
        "</StructureMember>"
        '<DataValueMember Name="Count" DataType="DINT" Value="9"/>'
        "</Structure>"
    )
    assert out == {"Msg": "hi", "Count": "9"}


def test_decorated_ascii_member_text_is_cleaned():
    # An ASCII member without a Value attribute carries its text as CDATA.
    out = flatten_decorated(
        '<Structure DataType="DemoUDT">'
        '<DataValueMember Name="Note" DataType="SINT" Radix="ASCII">\n\'x y\'\n</DataValueMember>'
        "</Structure>"
    )
    assert out == {"Note": "x y"}


def test_decorated_root_array_of_scalars():
    out = flatten_decorated(
        '<Array DataType="DINT" Dimensions="2">'
        '<Element Index="[0]" Value="1"/>'
        '<Element Index="[1]" Value="2"/>'
        "</Array>"
    )
    assert out == {"[0]": "1", "[1]": "2"}


def test_decorated_array_member_inside_structure():
    out = flatten_decorated(
        '<Structure DataType="DemoUDT">'
        '<ArrayMember Name="Counts" DataType="DINT" Dimensions="2">'
        '<Element Index="[0]" Value="4"/>'
        '<Element Index="[1]" Value="5"/>'
        "</ArrayMember>"
        "</Structure>"
    )
    assert out == {"Counts[0]": "4", "Counts[1]": "5"}


def test_decorated_array_of_structures():
    out = flatten_decorated(
        '<Array DataType="DemoUDT" Dimensions="1">'
        '<Element Index="[0]">'
        '<Structure DataType="DemoUDT">'
        '<DataValueMember Name="A" DataType="DINT" Value="1"/>'
        "</Structure>"
        "</Element>"
        "</Array>"
    )
    assert out == {"[0].A": "1"}


def test_decorated_multi_dim_index_kept_verbatim():
    out = flatten_decorated(
        '<Array DataType="DINT" Dimensions="2,3">'
        '<Element Index="[1,2]" Value="6"/>'
        "</Array>"
    )
    assert out == {"[1,2]": "6"}


def test_decorated_array_element_wrapping_string_structure():
    out = flatten_decorated(
        '<Array DataType="STRING" Dimensions="1">'
        '<Element Index="[0]">'
        '<Structure DataType="STRING">'
        '<DataValueMember Name="LEN" DataType="DINT" Value="3"/>'
        '<DataValueMember Name="DATA" DataType="SINT" Radix="ASCII">\'txt\'</DataValueMember>'
        "</Structure>"
        "</Element>"
        "</Array>"
    )
    assert out == {"[0]": "txt"}


# ---------------------------------------------------------------------------
# _flatten_xml
# ---------------------------------------------------------------------------


def test_flatten_xml_attrs_and_text():
    out = flatten_xml('<Root A="1"><Child B="2">hello</Child></Root>')
    assert out == {"@A": "1", "Child.@B": "2", "Child.#text": "hello"}


def test_flatten_xml_whitespace_only_text_omitted():
    out = flatten_xml("<Root>\n  <Child/>\n</Root>")
    assert out == {}


def test_flatten_xml_repeated_siblings_are_indexed():
    out = flatten_xml(
        '<Root><Provider Id="1"/><Provider Id="2"/><Other Id="3"/></Root>'
    )
    assert out == {
        "Provider[0].@Id": "1",
        "Provider[1].@Id": "2",
        "Other.@Id": "3",  # unique siblings keep their plain name
    }


def test_flatten_xml_index_kept_in_deeper_prefixes():
    out = flatten_xml('<Root><P><X V="a"/></P><P><X V="b"/></P></Root>')
    assert out == {"P[0].X.@V": "a", "P[1].X.@V": "b"}


def test_flatten_xml_nested_path_with_text_and_attrs():
    out = flatten_xml('<Root><A><B C="9">deep</B></A></Root>')
    assert out == {"A.B.@C": "9", "A.B.#text": "deep"}
