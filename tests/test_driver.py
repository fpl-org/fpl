"""Running a program never lets anything but an FplError out."""

import contextlib
from collections.abc import Callable

import pytest
from hypothesis import given
from hypothesis import strategies as st
from test_desugar import CURRY, programs

from fpl.driver import checked, printed, run, stacks
from fpl.errors import FplError
from fpl.types import reported

GOAL = "g : x -- x\n\t?\n"


@given(st.text(max_size=40))
def test_only_an_fpl_error_escapes(source: str) -> None:
    """Whatever text it is given, run returns or raises an FplError: nothing else escapes."""
    with contextlib.suppress(FplError):
        run(source)


def test_a_parse_is_not_yet_a_run() -> None:
    with pytest.raises(FplError) as caught:
        run("x\n")
    assert str(caught.value) == "ERROR: 1:1 no evaluator yet"


def attempt[T](thunk: Callable[[], T]) -> T | str:
    """What the thunk returns, or its error line."""
    try:
        return thunk()
    except FplError as error:
        return str(error)


@given(st.sampled_from(["", CURRY, GOAL]), programs)
def test_running_is_checking_then_stacks_then_printing(head: str, body: str) -> None:
    """[law: driver-split] run(s) is printed(stacks(checked(s))) with the same goals reported, and
    each stack is paired with the line of the run that left it."""
    source = head + body + "\n"
    said: list[str] = []
    split: list[str] = []

    def composed() -> str:
        statements, goals = checked(source)
        split.extend(reported(goal) for goal in goals)
        return printed(stacks(statements))

    assert attempt(lambda: run(source, said.append)) == attempt(composed)
    assert said == split
    first = head.count("\n") + 1
    lines = attempt(lambda: [line for line, _ in stacks(checked(source)[0])])
    assert isinstance(lines, str) or lines == list(range(first, first + body.count("\n") + 1))
