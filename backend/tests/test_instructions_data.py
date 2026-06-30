"""Guards for the built-in instruction reference data.

The ladder renderer trusts this table for glyphs and operand labels, so pin
its schema and a few stable, well-known entries. The exact operand wording can
grow, but these spot-checks should not regress.
"""
from parsers.rll.instructions import instruction_table

_DISPLAYS = {"contact", "coil", "box"}
_CONTACT_FORMS = {"no", "nc"}
_COIL_FORMS = {"ote", "otl", "otu"}
_ROLES = {"input", "output"}


def test_table_loads_and_is_cached():
    a = instruction_table()
    b = instruction_table()
    assert a is b  # cached, loaded once
    assert len(a) > 100


def test_every_entry_has_a_valid_shape():
    for mnem, spec in instruction_table().items():
        assert set(spec) >= {"display", "operands", "role"}, mnem
        assert spec["display"] in _DISPLAYS, mnem
        assert spec["role"] in _ROLES, mnem
        assert isinstance(spec["operands"], list), mnem
        assert all(isinstance(o, str) for o in spec["operands"]), mnem
        if spec["display"] == "contact":
            assert spec["form"] in _CONTACT_FORMS, mnem
            assert spec["role"] == "input", mnem  # a contact reads a bit
            assert spec["operands"] == [], mnem  # the tag is the label
        elif spec["display"] == "coil":
            assert spec["form"] in _COIL_FORMS, mnem
            assert spec["role"] == "output", mnem  # a coil drives a bit
            assert spec["operands"] == [], mnem


def test_known_contacts_and_coils():
    t = instruction_table()
    assert (t["XIC"]["display"], t["XIC"]["form"]) == ("contact", "no")
    assert (t["XIO"]["display"], t["XIO"]["form"]) == ("contact", "nc")
    assert (t["OTE"]["display"], t["OTE"]["form"]) == ("coil", "ote")
    assert (t["OTL"]["display"], t["OTL"]["form"]) == ("coil", "otl")
    assert (t["OTU"]["display"], t["OTU"]["form"]) == ("coil", "otu")


def test_known_box_operand_labels():
    t = instruction_table()
    assert t["MOV"]["operands"] == ["Source", "Dest"]
    assert t["EQU"]["operands"] == ["Source A", "Source B"]
    assert t["ADD"]["operands"] == ["Source A", "Source B", "Dest"]
    assert t["TON"]["operands"] == ["Timer", "Preset", "Accum"]
    assert t["CTU"]["operands"] == ["Counter", "Preset", "Accum"]
    assert t["LIM"]["operands"] == ["Low Limit", "Test", "High Limit"]


def test_known_io_roles():
    t = instruction_table()
    # Compare/test boxes read; they sit on the input (left) side of a rung.
    for read in ("EQU", "NEQ", "GRT", "LES", "GEQ", "MEQ", "LIM", "ONS"):
        assert t[read]["role"] == "input", read
    # Action boxes write; they sit on the output (right) side.
    for write in ("MOV", "ADD", "TON", "CTU", "MSG", "JSR"):
        assert t[write]["role"] == "output", write


def test_renamed_mnemonics_kept_as_aliases():
    # Logix Designer v36 renamed several instructions; ladder text from older
    # exports still uses the legacy mnemonic, so both must resolve.
    t = instruction_table()
    for legacy, current in [("EQU", "EQ"), ("MOV", "MOVE"), ("LIM", "LIMIT")]:
        assert legacy in t and current in t
        assert t[legacy]["operands"] == t[current]["operands"]
