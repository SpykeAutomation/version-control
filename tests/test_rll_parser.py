"""Tests for the RLL rung text parser (parsers.rll)."""
import pytest
from lark.exceptions import LarkError

from parsers.rll import RLLParser
from parsers.rll.models import ParsedRung, RLLBranch, RLLInstruction, RLLParam
from parsers.rll.parser import RLLParseError


# ---------------------------------------------------------------------------
# Basic structure
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["", "   ", "\n"])
def test_empty_input_returns_empty_rung(rll, text):
    assert rll.parse(text) == ParsedRung()


def test_bare_semicolon_is_empty_rung(rll):
    assert rll.parse(";").elements == []


def test_nop_has_no_params(rll):
    rung = rll.parse("NOP();")
    assert rung.elements == [RLLInstruction(name="NOP", params=[])]


def test_sequential_instructions(rll):
    rung = rll.parse("XIC(StartPB)OTE(RunLamp);")
    assert [e.name for e in rung.elements] == ["XIC", "OTE"]
    assert rung.elements[0].params[0].text == "StartPB"
    assert rung.elements[1].params[0].text == "RunLamp"


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------


def test_empty_middle_param(rll):
    rung = rll.parse("GSV(WallClockTime,,LocalDateTime,TimeBuf);")
    params = rung.elements[0].params
    assert len(params) == 4
    assert params[1].is_empty
    assert [p.text for p in params] == [
        "WallClockTime",
        "",
        "LocalDateTime",
        "TimeBuf",
    ]


def test_trailing_empty_param(rll):
    params = rll.parse("MOV(SrcVal,DstVal,);").elements[0].params
    assert len(params) == 3
    assert params[2].is_empty


def test_question_mark_params(rll):
    params = rll.parse("TON(DelayTmr,?,?);").elements[0].params
    assert [p.text for p in params] == ["DelayTmr", "?", "?"]


def test_multi_word_unquoted_param(rll):
    params = rll.parse("DCS(SafeIn,EMERGENCY STOP);").elements[0].params
    assert params[1].tokens == ["EMERGENCY", "STOP"]
    assert params[1].text == "EMERGENCY STOP"


def test_io_path_param_round_trips(rll):
    param = rll.parse("XIC(Rack1:1:I.Data.3);").elements[0].params[0]
    assert param.text == "Rack1:1:I.Data.3"


def test_cross_program_reference(rll):
    param = rll.parse("OTE(\\ProgA.Status.PowerOn);").elements[0].params[0]
    assert param.tokens[0] == "\\"
    assert param.text == "\\ProgA.Status.PowerOn"


def test_string_literal_with_escape_is_one_token(rll):
    param = rll.parse("COP('AB$'CD',StrBuf,1);").elements[0].params[0]
    assert param.tokens == ["'AB$'CD'"]


def test_hex_and_binary_literals(rll):
    params = rll.parse("MOV(16#FF_0A,MaskWord);").elements[0].params
    assert params[0].tokens == ["16#FF_0A"]
    params = rll.parse("MOV(2#1010,MaskWord);").elements[0].params
    assert params[0].tokens == ["2#1010"]


def test_expression_param(rll):
    param = rll.parse("CMP(CntArr[2]+CntArr[3]<=2);").elements[0].params[0]
    assert param.tokens == [
        "CntArr", "[", "2", "]", "+", "CntArr", "[", "3", "]", "<=", "2",
    ]
    assert param.text == "CntArr[2]+CntArr[3]<=2"


def test_nested_paren_group(rll):
    param = rll.parse("CPT(DstVal,(InWord AND (InWord - 1)));").elements[0].params[1]
    assert param.tokens == [
        "(", "InWord", "AND", "(", "InWord", "-", "1", ")", ")",
    ]


def test_multi_dim_subscript(rll):
    param = rll.parse("MOV(0,AlarmWords[0,13]);").elements[0].params[1]
    assert param.tokens == ["AlarmWords", "[", "0", ",", "13", "]"]
    assert param.text == "AlarmWords[0,13]"


def test_subscript_with_expression_dims(rll):
    param = rll.parse("MOV(0,Grid[Idx+1,Col]);").elements[0].params[1]
    assert param.tokens == ["Grid", "[", "Idx", "+", "1", ",", "Col", "]"]


# ---------------------------------------------------------------------------
# Branches
# ---------------------------------------------------------------------------


def test_two_leg_branch_with_following_instruction(rll):
    rung = rll.parse("[XIC(SelA) ,XIC(SelB) ]OTE(AnySel);")
    branch, ote = rung.elements
    assert isinstance(branch, RLLBranch)
    assert len(branch.legs) == 2
    assert branch.legs[0][0].name == "XIC"
    assert branch.legs[1][0].params[0].text == "SelB"
    assert ote.name == "OTE"


def test_empty_branch_leg(rll):
    branch = rll.parse("[XIC(SelA) ,]OTE(AnySel);").elements[0]
    assert len(branch.legs) == 2
    assert branch.legs[1] == []


def test_three_leg_branch_with_multi_instruction_leg(rll):
    branch = rll.parse("[XIC(A1)XIO(A2),XIC(B1),XIC(C1)]OTE(OutBit);").elements[0]
    assert len(branch.legs) == 3
    assert [i.name for i in branch.legs[0]] == ["XIC", "XIO"]
    assert [i.name for i in branch.legs[1]] == ["XIC"]


def test_nested_branch_inside_leg(rll):
    branch = rll.parse("[XIC(A1)[XIC(B1),XIC(B2)],XIC(C1)]OTE(OutBit);").elements[0]
    leg0 = branch.legs[0]
    assert isinstance(leg0[0], RLLInstruction)
    assert isinstance(leg0[1], RLLBranch)
    assert len(leg0[1].legs) == 2


def test_instruction_before_branch_keeps_order(rll):
    rung = rll.parse("XIC(Gate)[OTE(OutA),OTE(OutB)];")
    assert isinstance(rung.elements[0], RLLInstruction)
    assert isinstance(rung.elements[1], RLLBranch)


# ---------------------------------------------------------------------------
# RLLParam.text spacing rules
# ---------------------------------------------------------------------------


def test_param_text_spacing():
    assert RLLParam(tokens=["A", "B"]).text == "A B"  # word-word gets a space
    assert RLLParam(tokens=["A", "+", "B"]).text == "A+B"
    assert RLLParam(tokens=["Units", "per", "sec"]).text == "Units per sec"
    assert RLLParam(tokens=["2", "Items"]).text == "2 Items"  # digits are words
    assert RLLParam(tokens=[]).text == ""


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def test_unbalanced_paren_raises(rll):
    with pytest.raises(RLLParseError) as exc_info:
        rll.parse("XIC(StartPB;")
    err = exc_info.value
    assert err.rung_text == "XIC(StartPB;"
    assert isinstance(err.cause, LarkError)


def test_missing_terminator_raises(rll):
    with pytest.raises(RLLParseError):
        rll.parse("XIC(StartPB)")


def test_long_rung_error_message_is_truncated(rll):
    bad = "XIC(" + "A" * 130  # unbalanced, and longer than the 120-char preview
    with pytest.raises(RLLParseError) as exc_info:
        rll.parse(bad)
    assert "..." in str(exc_info.value)


# ---------------------------------------------------------------------------
# Scientific notation
# ---------------------------------------------------------------------------


def test_scientific_notation_is_single_token(rll):
    param = rll.parse("MOV(2.0e5,RateSet);").elements[0].params[0]
    assert param.tokens == ["2.0e5"]


def test_scientific_notation_signed_exponent_is_single_token(rll):
    param = rll.parse("MOV(2.5E-3,Gain);").elements[0].params[0]
    assert param.tokens == ["2.5E-3"]
