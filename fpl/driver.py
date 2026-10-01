"""parse, then everything after it. Shared by the command line and the tests."""

from collections.abc import Callable

from fpl.desugar import desugar, listing
from fpl.eval import evaluate
from fpl.parse import parse
from fpl.print import render
from fpl.types import elaborate, reported


def silent(_line: str) -> None:
    """Goals go nowhere."""


def run(source: str, report: Callable[[str], None] = silent) -> str:
    """What running the program prints: the stack each line leaves, a line each, as the printer
    writes it (hole program-output). Definitions print nothing; every body is checked against its
    effect line, and each goal met is handed to `report`, before any line runs."""
    statements = desugar(parse(source))
    for goal in elaborate(statements)[1]:
        report(reported(goal))
    return render(listing(evaluate(statements)))
