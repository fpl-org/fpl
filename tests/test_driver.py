"""Running a program never lets anything but an FplError out."""

import contextlib

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fpl.driver import run
from fpl.errors import FplError


@given(st.text(max_size=40))
def test_only_an_fpl_error_escapes(source: str) -> None:
    """Whatever text it is given, run returns or raises an FplError: nothing else escapes."""
    with contextlib.suppress(FplError):
        run(source)


def test_a_parse_is_not_yet_a_run() -> None:
    with pytest.raises(FplError) as caught:
        run("x\n")
    assert str(caught.value) == "ERROR: 1:1 no evaluator yet"
