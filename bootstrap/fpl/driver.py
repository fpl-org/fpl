"""parse, then everything after it. Shared by the command line and the tests."""

from collections.abc import Callable

from fpl.ast_core import Run, Statement
from fpl.desugar import desugar, listing
from fpl.eval import Stack, evaluate
from fpl.parse import parse
from fpl.print import render
from fpl.types import Goal, elaborate, reported

type Lines = tuple[tuple[int, Stack], ...]


def silent(_line: str) -> None:
    """Goals go nowhere."""


def checked(source: str) -> tuple[tuple[Statement, ...], tuple[Goal, ...]]:
    """The program's statements, every body checked against its effect line, and the goals met,
    in the order written."""
    statements = desugar(parse(source))
    return statements, elaborate(statements)[1]


def stacks(statements: tuple[Statement, ...], fuel: int | None = None) -> Lines:
    """Each run line's line and the stack it leaves, within fuel steps a line, or with no bound
    when fuel is None."""
    lines = (s.span.line for s in statements if isinstance(s, Run))
    return tuple(zip(lines, evaluate(statements, fuel), strict=True))


def printed(left: Lines) -> str:
    """What the stacks print: the stack each line leaves, a line each, as the printer writes it
    (hole program-output)."""
    return render(listing(tuple(stack for _, stack in left)))


def run(source: str, report: Callable[[str], None] = silent) -> str:
    """What running the program prints. Definitions print nothing; each goal met is handed to
    `report` before any line runs."""
    statements, goals = checked(source)
    for goal in goals:
        report(reported(goal))
    return printed(stacks(statements))
