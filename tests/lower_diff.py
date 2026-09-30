"""The differential harness: a program's output through the walker and through A (design 8)."""

from fpl.ast_core import Statement
from fpl.desugar import listing
from fpl.driver import run
from fpl.errors import FplError
from fpl.eval import evaluate
from fpl.print import render


def walker_output(source: str) -> str:
    """What `driver.run` prints, or its error line."""
    try:
        return run(source)
    except FplError as error:
        return str(error)


def evaluated(statements: tuple[Statement, ...]) -> str:
    """What the walker prints for elaborated core, or its error line."""
    try:
        return render(listing(evaluate(statements)))
    except FplError as error:
        return str(error)
