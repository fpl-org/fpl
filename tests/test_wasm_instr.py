"""The invariants of fpl.asm.wasm's instructions: a value that breaks one never exists."""

from collections.abc import Callable
from typing import get_args

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fpl.asm.wasm.instr import Const, Cvtop, Instr, Unop
from fpl.asm.wasm.types import WIDTH, NumType

numtypes = st.sampled_from(get_args(NumType))


@given(numtypes, st.integers(min_value=-(2**65), max_value=2**65))
def test_a_constant_is_an_unsigned_value_of_its_width(t: NumType, value: int) -> None:
    if 0 <= value < 2 ** WIDTH[t]:
        assert Const(t, value).value == value
    else:
        with pytest.raises(ValueError, match="outside"):
            Const(t, value)


@pytest.mark.parametrize("t", get_args(NumType))
def test_a_constant_ends_just_below_two_to_the_width(t: NumType) -> None:
    top = 2 ** WIDTH[t]
    assert (Const(t, 0).value, Const(t, top - 1).value) == (0, top - 1)
    for outside in (-1, top):
        with pytest.raises(ValueError, match="outside"):
            Const(t, outside)


@pytest.mark.parametrize(
    ("make", "exists"),
    [
        (lambda: Unop("i64", "extend32_s"), True),
        (lambda: Unop("i32", "extend16_s"), True),
        (lambda: Unop("i32", "extend32_s"), False),
        (lambda: Cvtop("i32", "wrap", "i64"), True),
        (lambda: Cvtop("i64", "extend_s", "i32"), True),
        (lambda: Cvtop("i64", "extend_u", "i32"), True),
        (lambda: Cvtop("i64", "wrap", "i64"), False),
        (lambda: Cvtop("i32", "wrap", "i32"), False),
        (lambda: Cvtop("i32", "extend_u", "i32"), False),
        (lambda: Cvtop("i64", "extend_s", "i64"), False),
        (lambda: Cvtop("i32", "extend_s", "i64"), False),
    ],
)
def test_an_operator_exists_only_in_the_shapes_the_spec_gives_it(
    make: Callable[[], Instr], exists: bool
) -> None:
    """The fixed violation tests of unop_fits and cvtop_shape: each shape the grammar has
    builds, and each one next to it is refused."""
    if exists:
        assert make() == make()
    else:
        with pytest.raises(ValueError, match="does not exist"):
            make()
