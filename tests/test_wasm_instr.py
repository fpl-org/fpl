"""The invariants of fpl.asm.wasm's instructions: a value that breaks one never exists."""

from collections.abc import Callable
from typing import get_args

import icontract
import pytest
from hypothesis import given
from hypothesis import strategies as st

from fpl.asm.wasm.instr import (
    Br,
    BrIf,
    BrTable,
    Call,
    CallIndirect,
    Const,
    Cvtop,
    If,
    Instr,
    Load,
    MemArg,
    ReturnCall,
    ReturnCallIndirect,
    Store,
    Unop,
)
from fpl.asm.wasm.types import WIDTH, NumType, TypeUse

numtypes = st.sampled_from(get_args(NumType))


@given(numtypes, st.integers(min_value=-(2**65), max_value=2**65))
def test_a_constant_is_an_unsigned_value_of_its_width(t: NumType, value: int) -> None:
    if 0 <= value < 2 ** WIDTH[t]:
        assert Const(t, value).value == value
    else:
        with pytest.raises(ValueError, match=r"is outside 0 <= value < 2\*\*(32|64)$"):
            Const(t, value)


@pytest.mark.parametrize("t", get_args(NumType))
def test_a_constant_ends_just_below_two_to_the_width(t: NumType) -> None:
    top = 2 ** WIDTH[t]
    assert (Const(t, 0).value, Const(t, top - 1).value) == (0, top - 1)
    for outside in (-1, top):
        with pytest.raises(ValueError, match=r"is outside 0 <= value < 2\*\*(32|64)$"):
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
        (lambda: Load("i32", MemArg(0, 0), (16, "s")), True),
        (lambda: Load("i32", MemArg(0, 0), (32, "u")), False),
        (lambda: Load("i64", MemArg(0, 0), (32, "s")), True),
        (lambda: Load("i32", MemArg(0, 0), None), True),
        (lambda: Store("i32", MemArg(0, 0), 16), True),
        (lambda: Store("i32", MemArg(0, 0), 32), False),
        (lambda: Store("i64", MemArg(0, 0), 32), True),
        (lambda: Store("i64", MemArg(0, 0), None), True),
    ],
)
def test_an_operator_exists_only_in_the_shapes_the_spec_gives_it(
    make: Callable[[], Instr], exists: bool
) -> None:
    """The fixed violation tests of unop_fits, cvtop_shape, load_pack_fits and
    store_size_fits: each shape the grammar has
    builds, and each one next to it is refused."""
    if exists:
        assert make() == make()
    else:
        with pytest.raises(ValueError, match="does not exist"):
            make()


@given(st.integers(min_value=0, max_value=2**32 - 1))
def test_a_control_instruction_keeps_its_arms_and_immediates(x: int) -> None:
    use = TypeUse(x)
    br, br_if, table = Br(x), BrIf(x), BrTable((x,), x)
    branch = If("i32", (br,), (br_if, table))
    assert (branch.then, branch.else_) == ((br,), (br_if, table))
    assert (br.label, br_if.label, table.labels, table.default) == (x, x, (x,), x)
    assert [c.func for c in (Call(x), ReturnCall(x))] == [x, x]
    indirect = (CallIndirect(x, use), ReturnCallIndirect(x, use))
    assert [(c.table, c.type) for c in indirect] == [(x, use), (x, use)]


@given(st.integers(min_value=-1, max_value=64), st.integers(min_value=-1, max_value=2**32))
def test_a_memarg_holds_an_exponent_below_64_and_a_u32(align: int, offset: int) -> None:
    """The violation test of memarg_in_range, at each bound and one past it."""
    if 0 <= align < 64 and 0 <= offset < 2**32:
        arg = MemArg(align, offset)
        assert (arg.align, arg.offset) == (align, offset)
    else:
        with pytest.raises(icontract.ViolationError):
            MemArg(align, offset)


@pytest.mark.parametrize(("align", "offset"), [(-1, 0), (64, 0), (0, -1), (0, 2**32)])
def test_a_memarg_refuses_one_past_each_bound(align: int, offset: int) -> None:
    assert MemArg(63, 2**32 - 1).align == 63
    with pytest.raises(icontract.ViolationError):
        MemArg(align, offset)
