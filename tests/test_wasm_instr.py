"""The invariants of fpl.asm.wasm's instructions: a value that breaks one never exists."""

from typing import get_args

import icontract
import pytest
from hypothesis import given
from hypothesis import strategies as st

from fpl.asm.wasm.instr import Const
from fpl.asm.wasm.types import WIDTH, NumType

numtypes = st.sampled_from(get_args(NumType))


@given(numtypes, st.integers(min_value=-(2**65), max_value=2**65))
def test_a_constant_is_an_unsigned_value_of_its_width(t: NumType, value: int) -> None:
    if 0 <= value < 2 ** WIDTH[t]:
        assert Const(t, value).value == value
    else:
        with pytest.raises(icontract.ViolationError):
            Const(t, value)


@pytest.mark.parametrize("t", get_args(NumType))
def test_a_constant_ends_just_below_two_to_the_width(t: NumType) -> None:
    top = 2 ** WIDTH[t]
    assert (Const(t, 0).value, Const(t, top - 1).value) == (0, top - 1)
    for outside in (-1, top):
        with pytest.raises(icontract.ViolationError):
            Const(t, outside)
