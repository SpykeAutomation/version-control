"""AOI operand labels come from the project's own AOI definitions.

These build AOI definitions and check that an instance call's operand rows
pick up the right parameter names.
"""
from diff.ladder import LabelResolver, aoi_operand_labels, classify
from parsers.l5x.models import AOI, AOIParameter
from parsers.rll.models import RLLInstruction, RLLParam


def _aoi(name, params):
    return AOI(name=name, parameters=[
        AOIParameter(name=n, data_type=dt, usage=u, required=req, visible=vis)
        for (n, dt, u, req, vis) in params
    ])


# A representative AOI: the auto enable params, two required args, one optional.
VALVE = _aoi("ValveCtl", [
    ("EnableIn", "BOOL", "Input", False, True),
    ("EnableOut", "BOOL", "Output", False, True),
    ("Command", "BOOL", "Input", True, True),
    ("Position", "REAL", "InOut", True, True),
    ("Tuning", "REAL", "Input", False, True),  # optional -> not passed in the call
])


def test_labels_skip_enable_params_and_optional_params():
    labels = aoi_operand_labels([VALVE])
    # backing tag (unlabeled), then the required params in order
    assert labels["ValveCtl"] == ["", "Command", "Position"]


def test_multiple_aois_each_keyed_by_name():
    other = _aoi("Pump", [("Run", "BOOL", "Input", True, True)])
    labels = aoi_operand_labels([VALVE, other])
    assert set(labels) == {"ValveCtl", "Pump"}
    assert labels["Pump"] == ["", "Run"]


def test_aoi_call_box_is_labelled_from_the_definition():
    resolver = LabelResolver(aoi_operands=aoi_operand_labels([VALVE]))
    call = RLLInstruction(
        name="ValveCtl",
        params=[RLLParam(tokens=t) for t in (["Valve1"], ["OpenCmd"], ["PosFb"])],
    )
    el = classify(call, resolver)
    assert el.kind == "box" and el.mnemonic == "ValveCtl"
    assert [(o.label, o.value) for o in el.operands] == [
        ("", "Valve1"),       # backing tag
        ("Command", "OpenCmd"),
        ("Position", "PosFb"),
    ]


def test_builtin_wins_over_an_aoi_with_a_clashing_name():
    # A project cannot redefine a built-in; the built-in spec must take priority.
    resolver = LabelResolver(aoi_operands={"MOV": ["", "Bogus"]})
    assert resolver.lookup("MOV")["operands"] == ["Source", "Dest"]


def test_empty_aoi_list_gives_no_overlay():
    assert aoi_operand_labels([]) == {}
