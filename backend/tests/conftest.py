"""Shared parser fixtures.

Building a parser compiles its grammar, which is slow (especially for ST).
Each parser is therefore built once and shared by every test in the run;
parsing itself never mutates the parser, so sharing is safe.
"""
import pytest

from parsers.l5x import L5XParser
from parsers.rll import RLLParser
from parsers.st import STParser


@pytest.fixture(scope="session")
def l5x() -> L5XParser:
    return L5XParser()


@pytest.fixture(scope="session")
def rll() -> RLLParser:
    return RLLParser()


@pytest.fixture(scope="session")
def st() -> STParser:
    return STParser()
