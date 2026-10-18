"""A property that never draws the big number."""

from hypothesis import given
from hypothesis import strategies as st

from fpl.ok import double


@given(st.integers(min_value=0, max_value=100))
def test_double_is_adding_to_itself(n: int) -> None:
    assert double(n) == n + n
