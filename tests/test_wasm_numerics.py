"""The integer operators of 4.3.2: one definition per operator Literal, and the traps."""

from typing import get_args

import pytest
import wasm_strategies as legal
from hypothesis import given
from hypothesis import strategies as st
from wasm_oracle import Calls, Invoke, Item, Tools, run_wabt, run_wasmtime
from wasm_strategies import numtypes, operands

from fpl.asm.wasm.instr import (
    Binop,
    Cvtop,
    IBinop,
    ICvtop,
    IRelop,
    ITestop,
    IUnop,
    LocalGet,
    Relop,
    Unop,
)
from fpl.asm.wasm.instr import Testop as _Testop  # pytest would collect a Test* name
from fpl.asm.wasm.module import Export, Func, Module
from fpl.asm.wasm.numerics import BINOPS, CVTOPS, RELOPS, TESTOPS, UNOPS, Trap
from fpl.asm.wasm.text import print_module
from fpl.asm.wasm.types import WIDTH, FuncType, NumType

TABLES = [
    (UNOPS, IUnop),
    (BINOPS, IBinop),
    (TESTOPS, ITestop),
    (RELOPS, IRelop),
    (CVTOPS, ICvtop),
]


@pytest.mark.parametrize(("table", "names"), TABLES)
def test_each_table_defines_exactly_its_operators(table: dict[str, object], names: object) -> None:
    assert set(table) == set(get_args(names))


@pytest.mark.parametrize("n", [32, 64])
@pytest.mark.parametrize("op", ["div_s", "div_u", "rem_s", "rem_u"])
def test_a_zero_divisor_traps(n: int, op: IBinop) -> None:
    assert BINOPS[op](n, 7, 0) == Trap("integer divide by zero")


@pytest.mark.parametrize("n", [32, 64])
def test_the_one_signed_quotient_past_the_range_traps_and_its_remainder_is_zero(
    n: int,
) -> None:
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
    return (
        t,
        draw(st.sampled_from(get_args(IBinop))),
        draw(operands(t)),
        draw(operands(t)),
    )


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


Operator = Unop | Binop | _Testop | Relop | Cvtop
FAMILIES: list[tuple[Operator, ...]] = [
    legal.UNOPS, legal.BINOPS, legal.TESTOPS, legal.RELOPS, legal.CVTOPS
]  # fmt: skip


def mnemonic(op: Operator) -> str:
    """The operator's name in the text format, which also names its export."""
    if isinstance(op, Cvtop):
        return f"{op.to}.{op.op}_{op.source}"
    return f"{op.type}.{op.op}"


def signature(op: Operator) -> FuncType:
    """The operator's own type: its operands to its one result."""
    match op:
        case Unop() | Binop():
            return FuncType((op.type,) * (1 + isinstance(op, Binop)), (op.type,))
        case _Testop() | Relop():
            return FuncType((op.type,) * (1 + isinstance(op, Relop)), ("i32",))
        case Cvtop():
            return FuncType((op.source,), (op.to,))


def evaluate(op: Operator, args: tuple[int, ...]) -> int | Trap:
    """The operator applied to `args` by the tables of numerics.py."""
    match op:
        case Unop():
            return UNOPS[op.op](WIDTH[op.type], *args)
        case Binop():
            return BINOPS[op.op](WIDTH[op.type], *args)
        case _Testop():
            return TESTOPS[op.op](WIDTH[op.type], *args)
        case Relop():
            return RELOPS[op.op](WIDTH[op.type], *args)
        case Cvtop():
            return CVTOPS[op.op](*args)


def family_module(family: tuple[Operator, ...]) -> Module:
    """One function per operator, applying it to its parameters, exported under its mnemonic."""
    types = tuple(map(signature, family))
    funcs = tuple(
        Func(k, (), (*map(LocalGet, range(len(t.params))), op))
        for k, (op, t) in enumerate(zip(family, types, strict=True))
    )
    exports = tuple(Export(mnemonic(op), "func", k) for k, op in enumerate(family))
    return Module(types=types, funcs=funcs, exports=exports)


@st.composite
def invokes(draw: st.DrawFn, family: tuple[Operator, ...]) -> Invoke:
    """One operator of `family` on edge-biased operands, expecting what numerics.py gives."""
    op = draw(st.sampled_from(family))
    t = signature(op)
    args = tuple(draw(operands(p)) for p in t.params)
    result = evaluate(op, args)
    expect: tuple[tuple[NumType, int], ...] | str = (
        result.kind if isinstance(result, Trap) else ((t.results[0], result),)
    )
    return Invoke(mnemonic(op), tuple(zip(t.params, args, strict=True)), expect)


def family_calls(family: tuple[Operator, ...]) -> st.SearchStrategy[Calls]:
    """The family's module, and many invocations of it."""
    text = print_module(family_module(family))
    return st.lists(invokes(family), min_size=1, max_size=16).map(lambda i: Calls(text, tuple(i)))


@given(st.tuples(*map(family_calls, FAMILIES)))
def test_every_integer_operator_agrees_with_both_engines(
    wasm_tools: Tools, batch: tuple[Calls, ...]
) -> None:
    """[law: numerics-agree] For every integer operator of the subset and drawn operands biased
    to 0, 1, -1, the signed extremes and shift counts at and beyond N, the evaluator's result or
    trap kind equals wasmtime's and wabt's.

    One module per operator family, one directive per drawn invocation.
    """
    items: list[Item] = list(batch)
    for report in (run_wabt(wasm_tools, items), run_wasmtime(wasm_tools, items)):
        assert report.wrong == (), report.output
