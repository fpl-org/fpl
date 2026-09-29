"""A step budget per run line, the runs nested in it counted, and a recursion too deep for the
walker refused at the line that ran it."""

import pytest
from hypothesis import given
from hypothesis import strategies as st
from test_desugar import CURRY, lines

import fpl.eval
from fpl.ast_core import Statement, Strand
from fpl.desugar import desugar
from fpl.driver import run, stacks
from fpl.errors import FplError
from fpl.eval import Stack, State, evaluate
from fpl.parse import parse

NESTED = "1 2 3 [1 +] each"


def outcome(statements: tuple[Statement, ...], *fuel: int) -> tuple[Stack, ...] | str:
    """The stacks the run lines leave, or the error line."""
    try:
        return evaluate(statements, *fuel)
    except FplError as error:
        return str(error)


@given(
    st.sampled_from(["", CURRY, "nop : --\n"]),
    st.integers(0, 2),
    st.one_of(lines.map(" | ".join), st.just(NESTED)),
)
def test_fuel_bounds_the_steps_of_a_run_line(head: str, blanks: int, line: str) -> None:
    """[law: fuel] With fuel n a run line of n steps completes as it does with no fuel, and with
    n-1 it stops with out of fuel at its line; the steps of the runs nested in it count."""
    source = head + "\n" * blanks + line + "\n"
    statements = desugar(parse(source))
    steps = 0
    walked = fpl.eval.step

    def counted(state: State) -> State:
        nonlocal steps
        steps += 1
        return walked(state)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("fpl.eval.step", counted)
        today = outcome(statements)
    assert steps > 0
    assert outcome(statements, steps) == today
    assert outcome(statements, steps - 1) == f"ERROR: {source.count(chr(10))}:1 out of fuel"


def test_a_nested_run_spends_the_line_fuel() -> None:
    """each runs its quotation once per item, and each of those steps is the line's."""
    statements = desugar(parse("x : --\n\n" + NESTED + "\n"))
    assert outcome(statements, 10) == ((Strand((2, 3, 4)),),)
    assert outcome(statements, 9) == "ERROR: 3:1 out of fuel"


def test_each_run_line_has_its_fuel() -> None:
    """The budget is a run line's, not the program's: two lines of ten steps complete with ten,
    and with nine the costly line fails at its own line."""
    both = desugar(parse("x : --\n\n" + NESTED + "\n" + NESTED + "\n"))
    assert outcome(both, 10) == ((Strand((2, 3, 4)),), (Strand((2, 3, 4)),))
    assert outcome(both, 9) == "ERROR: 3:1 out of fuel"
    second = desugar(parse("1\n" + NESTED + "\n"))
    assert outcome(second, 9) == "ERROR: 2:1 out of fuel"
    with pytest.raises(FplError, match=r"^ERROR: 2:1 out of fuel$"):
        stacks(second, 9)


def test_a_recursion_too_deep_is_an_error_at_its_line() -> None:
    """A word that calls itself with no end exhausts the walker's stack, not the program's."""
    with pytest.raises(FplError) as caught:
        run("f : x -- y\n\t1 2 [f] each\n1 f\n")
    assert str(caught.value) == "ERROR: 3:1 recursion too deep"
