"""Tests for the Structured Text parser (parsers.st).

The parser does not echo input text back. It rebuilds expression text from
the parse tree with its own spacing rules: one space around binary
operators and after index commas (``Grid[i,j]`` comes back as
``Grid[i, j]``). The string assertions below expect that rebuilt form, so
an assertion that doesn't match its input verbatim is intentional.
"""
import pytest
from lark.exceptions import LarkError

from parsers.st import STParser
from parsers.st.models import ParsedST
from parsers.st.parser import STParseError


def stmt(st: STParser, text: str):
    """Parse a single statement and return it."""
    statements = st.parse(text).statements
    assert len(statements) == 1
    return statements[0]


# ---------------------------------------------------------------------------
# Assignments and expression reconstruction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["", "   ", "\n\n"])
def test_empty_input_returns_empty_result(st, text):
    assert st.parse(text) == ParsedST()


def test_simple_assignment(st):
    s = stmt(st, "CycleCount := 100;")
    assert s.kind == "assign"
    assert s.assignment.target == "CycleCount"
    assert s.assignment.value == "100"


def test_array_assignment_operator(st):
    s = stmt(st, "OutBuf [:=] 5;")
    assert s.kind == "assign"
    assert s.assignment.target == "OutBuf"
    assert s.assignment.value == "5"


def test_member_chain_target(st):
    s = stmt(st, "Recipe.Step.Time := 5;")
    assert s.assignment.target == "Recipe.Step.Time"


def test_index_access_is_canonicalized(st):
    # Reconstruction inserts a space after index commas.
    s = stmt(st, "Grid[RowIdx,ColIdx] := 1;")
    assert s.assignment.target == "Grid[RowIdx, ColIdx]"


def test_bit_access(st):
    s = stmt(st, "StatusWord.0 := 1;")
    assert s.assignment.target == "StatusWord.0"


def test_dynamic_bit_access(st):
    s = stmt(st, "StatusWord.[BitIdx] := 1;")
    assert s.assignment.target == "StatusWord.[BitIdx]"


def test_dynamic_bit_access_with_expression_index(st):
    s = stmt(st, "Flag := StatusWord.[BitIdx + 1];")
    assert s.assignment.value == "StatusWord.[BitIdx + 1]"


def test_cross_program_reference_with_colon(st):
    s = stmt(st, "Mirror := \\ProgA:SubProg.RunFlag;")
    assert s.assignment.value == "\\ProgA:SubProg.RunFlag"


def test_cross_program_reference_without_colon(st):
    s = stmt(st, "Mirror := \\ProgA.RunFlag;")
    assert s.assignment.value == "\\ProgA.RunFlag"


def test_operator_precedence_reconstruction(st):
    s = stmt(st, "Result := BaseVal + Gain * 3;")
    assert s.assignment.value == "BaseVal + Gain * 3"


def test_paren_expr_reconstruction(st):
    s = stmt(st, "Result := (BaseVal + Gain) * 3;")
    assert s.assignment.value == "(BaseVal + Gain) * 3"


def test_unary_minus_is_space_joined(st):
    s = stmt(st, "Offset := -Trim;")
    assert s.assignment.value == "- Trim"


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("Mask := 16#FF;", "16#FF"),
        ("Mask := 2#1010;", "2#1010"),
        ("Msg := 'AB$'CD';", "'AB$'CD'"),
    ],
)
def test_literal_values(st, text, value):
    assert stmt(st, text).assignment.value == value


# ---------------------------------------------------------------------------
# Calls
# ---------------------------------------------------------------------------


def test_call_statement(st):
    s = stmt(st, "MotorCtl(StartCmd,StopCmd);")
    assert s.kind == "call"
    assert s.call.name == "MotorCtl"
    assert s.call.args == ["StartCmd", "StopCmd"]


def test_call_with_empty_arg(st):
    s = stmt(st, "GSV(WallClockTime,,LocalDateTime,TimeBuf);")
    assert s.call.args == ["WallClockTime", None, "LocalDateTime", "TimeBuf"]


def test_call_with_no_args(st):
    s = stmt(st, "NOP();")
    assert s.kind == "call"
    assert s.call.args == []


def test_call_inside_assignment_lands_in_nested_calls(st):
    s = stmt(st, "Highest := MAX_OF(LeftVal, RightVal);")
    assert s.kind == "assign"
    # Calls collapse to "name(...)" in reconstructed expression text; the
    # full argument list is preserved on nested_calls.
    assert s.assignment.value == "MAX_OF(...)"
    assert len(s.nested_calls) == 1
    assert s.nested_calls[0].name == "MAX_OF"
    assert s.nested_calls[0].args == ["LeftVal", "RightVal"]


def test_call_argument_expressions_are_reconstructed(st):
    s = stmt(st, "PumpCtl(Level + 2, Mode);")
    assert s.call.args == ["Level + 2", "Mode"]


# ---------------------------------------------------------------------------
# IF / ELSIF / ELSE
# ---------------------------------------------------------------------------


def test_if_condition_and_body(st):
    s = stmt(st, "IF RunCmd THEN CycleCount := 0; NOP(); END_IF;")
    assert s.kind == "if"
    assert s.condition == "RunCmd"
    assert [c.kind for c in s.children] == ["assign", "call"]


def test_if_condition_with_call(st):
    s = stmt(st, "IF Enabled AND CheckOk(StnNo) > 1 THEN CycleCount := 0; END_IF;")
    assert s.condition == "Enabled AND CheckOk(...) > 1"
    assert len(s.nested_calls) == 1
    assert s.nested_calls[0].name == "CheckOk"
    assert s.nested_calls[0].args == ["StnNo"]


def test_elsif_and_else_clauses(st):
    s = stmt(
        st,
        "IF ModeSel = 1 THEN StepNo := 1;"
        " ELSIF ModeSel = 2 THEN StepNo := 2;"
        " ELSE StepNo := 0; END_IF;",
    )
    kinds = [c.kind for c in s.children]
    assert kinds == ["assign", "elsif", "else"]
    elsif = s.children[1]
    assert elsif.condition == "ModeSel = 2"
    assert [c.kind for c in elsif.children] == ["assign"]
    assert [c.kind for c in s.children[2].children] == ["assign"]


def test_nested_if(st):
    s = stmt(st, "IF OuterOk THEN IF InnerOk THEN StepNo := 1; END_IF; END_IF;")
    inner = s.children[0]
    assert inner.kind == "if"
    assert inner.condition == "InnerOk"
    assert [c.kind for c in inner.children] == ["assign"]


def test_call_in_body_does_not_leak_into_if_nested_calls(st):
    s = stmt(st, "IF RunCmd THEN MotorCtl(StartCmd); END_IF;")
    assert s.nested_calls == []  # only condition calls attach to the IF itself
    assert s.children[0].kind == "call"
    assert s.children[0].call.name == "MotorCtl"


# ---------------------------------------------------------------------------
# FOR / WHILE / REPEAT
# ---------------------------------------------------------------------------


def test_for_loop_metadata(st):
    s = stmt(st, "FOR LoopIdx := 0 TO 9 DO Totals[LoopIdx] := 0; END_FOR;")
    assert s.kind == "for"
    assert s.loop_var == "LoopIdx"
    assert s.loop_start == "0"
    assert s.loop_end == "9"
    assert s.loop_step is None
    assert s.iteration_bound == 10
    assert s.loop_header == "FOR LoopIdx := 0 TO 9"
    assert s.has_exit is False


def test_for_loop_with_by_clause(st):
    s = stmt(st, "FOR LoopIdx := 0 TO 9 BY 2 DO NOP(); END_FOR;")
    assert s.loop_step == "2"
    assert s.iteration_bound == 5
    assert s.loop_header == "FOR LoopIdx := 0 TO 9 BY 2"


def test_for_loop_with_variable_bound(st):
    s = stmt(st, "FOR LoopIdx := 0 TO LastIdx DO NOP(); END_FOR;")
    assert s.loop_end == "LastIdx"
    assert s.iteration_bound is None


def test_for_loop_nested_exit_sets_has_exit(st):
    s = stmt(
        st,
        "FOR LoopIdx := 0 TO 9 DO"
        " IF AbortReq THEN EXIT; END_IF;"
        " END_FOR;",
    )
    assert s.has_exit is True


def test_while_loop(st):
    s = stmt(st, "WHILE HopperLevel < 50 DO HopperLevel := HopperLevel + 1; END_WHILE;")
    assert s.kind == "while"
    assert s.condition == "HopperLevel < 50"
    assert s.loop_header == "WHILE HopperLevel < 50"
    assert [c.kind for c in s.children] == ["assign"]


def test_repeat_loop(st):
    s = stmt(st, "REPEAT RetryCnt := RetryCnt + 1; UNTIL RetryCnt > 5; END_REPEAT;")
    assert s.kind == "repeat"
    assert s.condition == "RetryCnt > 5"
    assert s.loop_header == "REPEAT UNTIL RetryCnt > 5"
    assert [c.kind for c in s.children] == ["assign"]


# ---------------------------------------------------------------------------
# CASE
# ---------------------------------------------------------------------------


def test_case_branches_and_else(st):
    s = stmt(
        st,
        "CASE StepNo OF"
        " 1: OutA := 1;"
        " 2,3: OutB := 1;"
        " ELSE OutC := 1;"
        " END_CASE;",
    )
    assert s.kind == "case"
    assert [c.kind for c in s.children] == ["case_branch", "case_branch", "else"]
    assert [c.kind for c in s.children[0].children] == ["assign"]


def test_case_range_label(st):
    s = stmt(st, "CASE StepNo OF 1..3: OutA := 1; END_CASE;")
    assert [c.kind for c in s.children] == ["case_branch"]


# ---------------------------------------------------------------------------
# Misc statements and input handling
# ---------------------------------------------------------------------------


def test_standalone_exit_and_return(st):
    assert stmt(st, "EXIT;").kind == "exit"
    assert stmt(st, "RETURN;").kind == "return"


def test_lowercase_keywords(st):
    s = stmt(st, "if RunCmd then CycleCount := 1; end_if;")
    assert s.kind == "if"
    assert [c.kind for c in s.children] == ["assign"]


def test_comments_are_ignored(st):
    text = (
        "// line comment\n"
        "StepNo := 1; (* block comment *)\n"
        "#region setup\n"
        "OutA := 2; /* c-style */\n"
        "#endregion\n"
        "OutB := 3;\n"
    )
    kinds = [s.kind for s in st.parse(text).statements]
    assert kinds == ["assign", "assign", "assign"]


def test_parse_lines_equals_joined_parse(st):
    lines = ["StepNo := 1;", "IF RunCmd THEN StepNo := 2; END_IF;"]
    assert st.parse_lines(lines) == st.parse("\n".join(lines))


def test_multiple_statements_keep_order(st):
    parsed = st.parse("StepNo := 1; NOP(); EXIT;")
    assert [s.kind for s in parsed.statements] == ["assign", "call", "exit"]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def test_missing_end_if_raises(st):
    with pytest.raises(STParseError) as exc_info:
        st.parse("IF RunCmd THEN StepNo := 1;")
    err = exc_info.value
    assert err.text == "IF RunCmd THEN StepNo := 1;"
    assert isinstance(err.cause, LarkError)


def test_unlexable_input_raises(st):
    with pytest.raises(STParseError):
        st.parse("@@@")


def test_long_input_error_message_is_truncated(st):
    bad = "IF " + "RunCmd AND " * 20 + "THEN"  # unparseable and >120 chars
    with pytest.raises(STParseError) as exc_info:
        st.parse(bad)
    assert "..." in str(exc_info.value)


# ---------------------------------------------------------------------------
# Scientific notation
# ---------------------------------------------------------------------------


def test_scientific_notation_literal(st):
    s = stmt(st, "RateSet := 2.0e5;")
    assert s.assignment.value == "2.0e5"


def test_scientific_notation_signed_exponent(st):
    s = stmt(st, "Gain := 2.5E-3 + 1e+6;")
    assert s.assignment.value == "2.5E-3 + 1e+6"
