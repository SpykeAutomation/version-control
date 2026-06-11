"""Unit tests for the loop-analysis helpers in parsers.st.parser."""
import pytest

from parsers.st.models import STStatement
from parsers.st.parser import _has_exit_statement, _try_compute_iteration_bound


@pytest.mark.parametrize(
    ("start", "end", "step", "expected"),
    [
        ("0", "9", None, 10),  # default step of 1
        ("0", "9", "2", 5),
        ("0", "10", "3", 4),
        ("1", "1", None, 1),
        ("9", "0", "-1", 10),  # counting down
        ("10", "0", "-2", 6),
        ("0", "9", "0", None),  # zero step never terminates
        ("9", "0", None, 0),  # start past end with positive step
        ("0", "9", "-1", 0),  # start before end with negative step
        ("0", "n", None, None),  # non-literal end
        ("i", "9", None, None),  # non-literal start
        (None, "9", None, None),
        ("0", None, None, None),
        ("0.5", "9", None, None),  # int() rejects float text
    ],
)
def test_try_compute_iteration_bound(start, end, step, expected):
    assert _try_compute_iteration_bound(start, end, step) == expected


def test_has_exit_statement_direct_child():
    children = [STStatement(kind="assign"), STStatement(kind="exit")]
    assert _has_exit_statement(children) is True


def test_has_exit_statement_nested():
    children = [
        STStatement(
            kind="if",
            children=[STStatement(kind="if", children=[STStatement(kind="exit")])],
        )
    ]
    assert _has_exit_statement(children) is True


def test_has_exit_statement_absent():
    children = [
        STStatement(kind="assign"),
        STStatement(kind="if", children=[STStatement(kind="call")]),
    ]
    assert _has_exit_statement(children) is False
