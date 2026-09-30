"""The integer operators of 4.3.2: one definition per operator Literal, and the traps."""

from typing import get_args

import pytest
from hypothesis import given
from hypothesis import strategies as st
from wasm_strategies import numtypes, operands

from fpl.asm.wasm.instr import IBinop, ICvtop, IRelop, ITestop, IUnop
from fpl.asm.wasm.numerics import BINOPS, CVTOPS, RELOPS, TESTOPS, UNOPS, Trap
from fpl.asm.wasm.types import WIDTH, NumType

TABLES = [(UNOPS, IUnop), (BINOPS, IBinop), (TESTOPS, ITestop), (RELOPS, IRelop), (CVTOPS, ICvtop)]


@pytest.mark.parametrize(("table", "names"), TABLES)
def test_each_table_defines_exactly_its_operators(table: dict[str, object], names: object) -> None:
    assert set(table) == set(get_args(names))


@pytest.mark.parametrize("n", [32, 64])
@pytest.mark.parametrize("op", ["div_s", "div_u", "rem_s", "rem_u"])
def test_a_zero_divisor_traps(n: int, op: IBinop) -> None:
    assert BINOPS[op](n, 7, 0) == Trap("integer divide by zero")


@pytest.mark.parametrize("n", [32, 64])
def test_the_one_signed_quotient_past_the_range_traps_and_its_remainder_is_zero(n: int) -> None:
    low, minus_one = 1 << (n - 1), (1 << n) - 1
    assert BINOPS["div_s"](n, low, minus_one) == Trap("integer overflow")
    assert BINOPS["rem_s"](n, low, minus_one) == 0


def test_signed_division_rounds_toward_zero_and_the_remainder_takes_the_dividend_sign() -> None:
    minus_seven, two = (1 << 32) - 7, 2
    assert BINOPS["div_s"](32, minus_seven, two) == (1 << 32) - 3
    assert BINOPS["rem_s"](32, minus_seven, two) == (1 << 32) - 1


@st.composite
def binop_cases(draw: st.DrawFn) -> tuple[NumType, IBinop, int, int]:
    t = draw(numtypes)
    return t, draw(st.sampled_from(get_args(IBinop))), draw(operands(t)), draw(operands(t))


@given(binop_cases())
def test_a_binop_gives_an_unsigned_value_of_its_width_or_a_trap(
    case: tuple[NumType, IBinop, int, int],
) -> None:
    t, op, i, j = case
    result = BINOPS[op](WIDTH[t], i, j)
    assert isinstance(result, Trap) or 0 <= result < 1 << WIDTH[t]


@pytest.mark.parametrize(
    ("op", "n", "i", "result"),
    [
        ("clz", 32, 0, 32),
        ("ctz", 64, 0, 64),
        ("ctz", 32, 8, 3),
        ("popcnt", 32, 0xF0F0, 8),
        ("extend8_s", 32, 0x180, 0xFFFFFF80),
        ("extend16_s", 64, 0x7FFF, 0x7FFF),
        ("extend32_s", 64, 0x80000000, 0xFFFFFFFF80000000),
    ],
)
def test_a_unop_at_its_edges(op: IUnop, n: int, i: int, result: int) -> None:
    assert UNOPS[op](n, i) == result
