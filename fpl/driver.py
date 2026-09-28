"""parse, then everything after it. Shared by the command line and the tests."""

from fpl.errors import FplError, Span
from fpl.parse import parse


def run(source: str) -> str:
    """What running the program prints. There is no evaluator yet, so a parse is all it does."""
    parse(source)
    raise FplError(Span(1, 1), "no evaluator yet")
