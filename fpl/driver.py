"""parse, then everything after it. Shared by the command line and the tests."""

from pathlib import Path

from fpl.errors import FplError, Span
from fpl.parse import GRAMMAR, parse


def run(source: str, grammar: Path = GRAMMAR) -> str:
    """What running the program prints. There is no evaluator yet, so a parse is all it does."""
    parse(source, grammar)
    raise FplError(Span(1, 1), "no evaluator yet")
