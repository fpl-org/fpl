"""The differential harness: a program's output through the walker and through A (design 8)."""

from dataclasses import dataclass

from fpl.ast_core import Statement, Value
from fpl.cbpv.machine import Failed, OutOfFuel, Panicked, Returned, Run_, Val, run
from fpl.desugar import desugar, listing
from fpl.driver import run as walk
from fpl.errors import FplError
from fpl.eval import evaluate
from fpl.lower.label import label
from fpl.lower.polarise import Lowered, polarise
from fpl.lower.select import Refused, select
from fpl.lower.walker import Origin, error_line, signature, stack
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


def lowered(source: str) -> Lowered | str | Refused:
    """Pass 2's output for `source`: the walker's front end (its error line), then select and
    polarise (the first refusal)."""
    try:
        statements = desugar(parse(source))
        elaborate(statements)
    except FplError as error:
        return str(error)
    core = select(statements)
    return core if isinstance(core, Refused) else polarise(core)


def no_handler(op: str, _cap: Val, _arg: Val) -> Val:
    raise AssertionError(f"Σ_walker has no operation {op}")


@dataclass(frozen=True)
class Ran:
    """Each run line's run, and the origins that read its thunks back."""

    runs: tuple[Run_, ...]
    origins: tuple[Origin, ...]


def ran(source: str, *, labelled: bool = True) -> Ran | str | Refused:
    """`source` run after pass 3 (after pass 2 unless `labelled`), or what stopped it first.
    Running out of fuel fails: drawn programs terminate."""
    result = lowered(source)
    if not isinstance(result, tuple):
        return result
    program, extra, origins = result
    sig = signature(extra)
    if labelled:
        program = label(program, sig)
    runs = run(program, sig, fuel=10_000 + 100 * len(source), handler=no_handler)
    assert not any(isinstance(r.end, OutOfFuel) for r in runs), source
    return Ran(runs, origins)


def ended(r: Run_, origins: tuple[Origin, ...]) -> tuple[Value, ...] | str:
    """A run's stack as the walker's values, or its panic's or failure's error line."""
    if isinstance(r.end, Panicked | Failed):
        return error_line(r.end)
    assert isinstance(r.end, Returned), r.end
    return stack(r.end.value, origins)


def cbpv_output(source: str, *, labelled: bool = True) -> str | Refused:
    """What A prints: each line run in order; the first panic's line replaces the output, as the
    walker's first error does."""
    result = ran(source, labelled=labelled)
    if not isinstance(result, Ran):
        return result
    stacks: list[tuple[Value, ...]] = []
    for r in result.runs:
        end = ended(r, result.origins)
        if isinstance(end, str):
            return end
        stacks.append(end)
    return render(listing(tuple(stacks)))
