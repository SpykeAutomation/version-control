"""Determinism guards.

Diffing only works if the same input always serializes to the exact same
JSON. These tests parse identical input twice — with separately built
parsers — and require byte-identical output, which catches any field that
depends on time, randomness, or parser state.
"""
from parsers.l5x import L5XParser
from parsers.l5x.models import L5XDocument
from parsers.rll import RLLParser
from parsers.st import STParser

from fixtures_l5x import KITCHEN_SINK


def test_l5x_output_is_identical_across_fresh_parsers():
    first = L5XParser().parse_string(KITCHEN_SINK).model_dump_json(indent=2)
    second = L5XParser().parse_string(KITCHEN_SINK).model_dump_json(indent=2)
    assert first == second


def test_parse_file_matches_parse_string(tmp_path):
    path = tmp_path / "doc.xml"
    path.write_text(KITCHEN_SINK, encoding="utf-8")
    parser = L5XParser()
    assert (
        parser.parse_file(str(path)).model_dump_json()
        == parser.parse_string(KITCHEN_SINK).model_dump_json()
    )


def test_l5x_json_round_trip():
    dump = L5XParser().parse_string(KITCHEN_SINK).model_dump_json()
    assert L5XDocument.model_validate_json(dump).model_dump_json() == dump


def test_rll_output_is_identical_across_fresh_parsers():
    rung = "[XIC(SelA) ,XIC(SelB) ]CMP(CntArr[2]+CntArr[3]<=2)OTE(AnySel);"
    first = RLLParser().parse(rung).model_dump_json()
    second = RLLParser().parse(rung).model_dump_json()
    assert first == second


def test_st_output_is_identical_across_fresh_parsers():
    text = (
        "IF Enabled AND CheckOk(StnNo) > 1 THEN\n"
        "  FOR LoopIdx := 0 TO 9 BY 2 DO Totals[LoopIdx] := 0; END_FOR;\n"
        "END_IF;\n"
        "GSV(WallClockTime,,LocalDateTime,TimeBuf);"
    )
    first = STParser().parse(text).model_dump_json()
    second = STParser().parse(text).model_dump_json()
    assert first == second
