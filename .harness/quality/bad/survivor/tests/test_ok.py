"""A property that checks nothing about the value."""

from hypothesis import given
from hypothesis import strategies as st

from fpl.ok import double


@given(st.integers())
def test_double_returns_an_int(n: int) -> None:
    assert isinstance(double(n), int)
