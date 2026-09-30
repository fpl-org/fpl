"""The differential harness: a program's output through the walker and through A (design 8)."""

from fpl.ast_core import Statement, Value
from fpl.cbpv.machine import OutOfFuel, Panicked, Returned, Val, run
from fpl.desugar import desugar, listing
from fpl.driver import run as walk
from fpl.errors import FplError
from fpl.eval import evaluate
from fpl.lower.polarise import polarise
from fpl.lower.select import Refused, select
from fpl.lower.walker import error_line, signature, stack
from fpl.parse import parse
from fpl.print import render
from fpl.types import elaborate


def walker_output(source: str) -> str:
    """What `driver.run` prints, or its error line."""
    try:
        return walk(source)
    except FplError as error:
        return str(error)


def evaluated(statements: tuple[Statement, ...]) -> str:
    """What the walker prints for elaborated core, or its error line."""
    try:
        return render(listing(evaluate(statements)))
    except FplError as error:
        return str(error)


def no_handler(op: str, _cap: Val, _arg: Val) -> Val:
    raise AssertionError(f"Σ_walker has no operation {op}")


def cbpv_output(source: str) -> str | Refused:
    """What A prints: the walker's front end (its error line), then select (its refusal),
    polarise, and each line run in order; the first panic's line replaces the output, as the
    walker's first error does. Running out of fuel fails: drawn programs terminate."""
    try:
        statements = desugar(parse(source))
        elaborate(statements)
    except FplError as error:
        return str(error)
    core = select(statements)
    if isinstance(core, Refused):
        return core
    lowered = polarise(core)
    if isinstance(lowered, Refused):
        return lowered
    program, extra, origins = lowered
    stacks: list[tuple[Value, ...]] = []
    for r in run(program, signature(extra), fuel=10_000 + 100 * len(source), handler=no_handler):
        assert not isinstance(r.end, OutOfFuel), source
        if isinstance(r.end, Panicked):
            return error_line(r.end)
        assert isinstance(r.end, Returned), r.end
        stacks.append(stack(r.end.value, origins))
    return render(listing(tuple(stacks)))
