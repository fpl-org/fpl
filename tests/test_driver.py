"""Running a program never lets anything but an FplError out."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fpl.driver import run
from fpl.errors import FplError


@given(st.text(max_size=40))
def test_nothing_runs_yet(source: str) -> None:
    with pytest.raises(FplError):
        run(source)


def test_a_parse_is_not_yet_a_run() -> None:
    with pytest.raises(FplError) as caught:
        run("x\n")
    assert str(caught.value) == "ERROR: 1:1 no evaluator yet"
