"""parse, then everything after it. Shared by the command line and the tests."""

from fpl.desugar import desugar, listing
from fpl.eval import evaluate
from fpl.parse import parse
from fpl.print import render


def run(source: str) -> str:
    """What running the program prints: the stack each line leaves, a line each, as the printer
    writes it (hole program-output). Definitions print nothing."""
    return render(listing(evaluate(desugar(parse(source)))))
