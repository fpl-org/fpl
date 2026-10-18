"""The fixture's property."""

from hypothesis import given
from hypothesis import strategies as st

from fpl.ok import double


@given(st.integers())
def test_double_is_adding_to_itself(n: int) -> None:
    assert double(n) == n + n
