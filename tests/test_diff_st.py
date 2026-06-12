"""ST line matching and the formatting-only check."""
from diff.st import diff_st_lines
from parsers.l5x.models import STLine


def L(number, text):
    return STLine(number=number, level=0, text=text)


def _diff(old, new, st):
    return diff_st_lines(old, new, lambda: st)


BASE = [
    L(0, "StepNo := 1;"),
    L(1, "IF Enabled THEN"),
    L(2, "  Total := Total + 1;"),
    L(3, "END_IF;"),
]


def test_identical_is_empty(st):
    changes, formatting_only = _diff(BASE, [l.model_copy() for l in BASE], st)
    assert changes == [] and formatting_only is False


def test_added_line(st):
    new = BASE + [L(4, "Done := 1;")]
    changes, formatting_only = _diff(BASE, new, st)
    assert [(c.kind, c.new_number, c.new_text) for c in changes] == [
        ("added", 4, "Done := 1;")
    ]
    assert formatting_only is False


def test_removed_line(st):
    changes, _ = _diff(BASE, BASE[:2] + BASE[3:], st)
    assert [(c.kind, c.old_number) for c in changes] == [("removed", 2)]


def test_modified_line(st):
    new = [l.model_copy() for l in BASE]
    new[0] = L(0, "StepNo := 2;")
    changes, _ = _diff(BASE, new, st)
    assert [(c.kind, c.old_text, c.new_text) for c in changes] == [
        ("modified", "StepNo := 1;", "StepNo := 2;")
    ]


def test_spacing_change_is_formatting_only(st):
    new = [l.model_copy() for l in BASE]
    new[0] = L(0, "StepNo:=1;")
    changes, formatting_only = _diff(BASE, new, st)
    assert changes == [] and formatting_only is True


def test_keyword_case_is_formatting_only(st):
    new = [l.model_copy() for l in BASE]
    new[1] = L(1, "if Enabled then")
    new[3] = L(3, "end_if;")
    changes, formatting_only = _diff(BASE, new, st)
    assert changes == [] and formatting_only is True
