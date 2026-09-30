"""The evaluator of 4.6-4.7: soundness over the valid modules, and the branches no generator
reaches, pinned by fixed modules."""

import pytest
from hypothesis import given
from hypothesis import strategies as st
from wasm_strategies import operands, valid_modules

from fpl.asm.wasm.exec import (
    DEPTH,
    Exhausted,
    Instance,
    Outcome,
    OutOfSteps,
    Values,
    instantiate,
    invoke,
)
from fpl.asm.wasm.instr import (
    Binop,
    Block,
    Br,
    BrIf,
    BrTable,
    Call,
    CallIndirect,
    Const,
    Cvtop,
    Drop,
    GlobalGet,
    GlobalSet,
    If,
    Instr,
    Load,
    LocalGet,
    LocalSet,
    LocalTee,
    Loop,
    MemArg,
    MemorySize,
    Relop,
    Return,
    ReturnCall,
    ReturnCallIndirect,
    Select,
    Store,
    Unop,
    Unreachable,
)
from fpl.asm.wasm.instr import Testop as _Testop  # pytest would collect a Test* name
from fpl.asm.wasm.module import (
    Data,
    Elem,
    Func,
    FuncImport,
    Global,
    Import,
    Mem,
    Module,
    Table,
)
from fpl.asm.wasm.numerics import Trap
from fpl.asm.wasm.types import (
    WIDTH,
    FuncType,
    GlobalType,
    Limits,
    MemType,
    TableType,
    TypeUse,
)
from fpl.asm.wasm.valid import check


@given(valid_modules(closed=True), st.data())
def test_every_well_typed_run_ends_in_typed_values_a_trap_or_out_of_steps(
    module: Module, data: st.DataObject
) -> None:
    """[law: type-soundness] For every closed module the checker accepts and every exported
    function invoked on well-typed arguments under a step budget, the evaluator ends in values
    of the declared result types (each in 0..2**N-1), a trap, or out of steps, and never raises
    (spec 7.4).

    The budget stays below DEPTH: every call costs its instruction's step, so no run can reach
    the depth limit, and each budget cuts the run at a different point.
    """
    assert check(module) is None
    instance = instantiate(module)
    if isinstance(instance, Trap):
        return
    for export in (e for e in module.exports if e.kind == "func"):
        t = module.types[module.funcs[export.index].type]
        args = tuple(data.draw(operands(p)) for p in t.params)
        steps = data.draw(st.integers(min_value=0, max_value=DEPTH - 1))
        match invoke(instance, export.index, args, steps):
            case Values(values):
                typed = zip(t.results, values, strict=True)
                assert all(0 <= v < 1 << WIDTH[r] for r, v in typed)
            case Trap() | OutOfSteps():
                pass
            case outcome:
                pytest.fail(f"{outcome} under {steps} steps")


I32 = FuncType((), ("i32",))
ONE_PAGE = (Mem(MemType(Limits(1, 1))),)
FIVE = Func(0, (), (Const("i32", 5),))
TABLE = (Table(TableType(Limits(3, 3))),)


def i32(value: int) -> Const:
    return Const("i32", value)


def main(
    body: tuple[Instr, ...],
    *,
    types: tuple[FuncType, ...] = (I32,),
    funcs: tuple[Func, ...] = (),
    mems: tuple[Mem, ...] = (),
    globals_: tuple[Global, ...] = (),
    indirect: bool = False,
) -> Module:
    """A closed module whose function 0 has type 0 and one i32 local, over `body`; with
    `indirect`, a table of three whose element 0 is function 1, the rest null."""
    return Module(
        types=types,
        globals=globals_,
        mems=mems,
        tables=TABLE if indirect else (),
        funcs=(Func(0, ("i32",), body), *funcs),
        elems=(Elem(0, (i32(0),), (1,)),) if indirect else (),
    )


def started(module: Module) -> Instance:
    instance = instantiate(module)
    assert isinstance(instance, Instance)
    return instance


AT0 = MemArg(0, 0)
DIVIDE = Trap("integer divide by zero")
OOB = Trap("out of bounds memory access")
UNARY = FuncType(("i32",), ("i32",))
CASES: list[tuple[str, Module, Outcome]] = [
    (
        "every numeric family",
        main((
            i32(8), Unop("i32", "ctz"), i32(3), Relop("i32", "eq"), _Testop("i32", "eqz"),
            Cvtop("i64", "extend_u", "i32"), Cvtop("i32", "wrap", "i64"),
        )),
        Values((0,)),
    ),
    (
        "out of two blocks, then return",
        main((Block(None, (Block(None, (Br(1),)),)), i32(6), Return(), i32(7))),
        Values((6,)),
    ),
    (
        "global.get",
        main((GlobalGet(0),), globals_=(Global(GlobalType(mutable=False, type="i32"), (i32(4),)),)),
        Values((4,)),
    ),
    ("select", main((i32(1), i32(2), i32(0), Select(None))), Values((2,))),
    ("tee", main((i32(3), LocalTee(0), LocalGet(0), Binop("i32", "add"))), Values((6,))),
    ("br_table default", main((Block("i32", (i32(4), i32(9), BrTable((1,), 0))),)), Values((4,))),
    (
        "loop counts down",
        main((
            i32(3), LocalSet(0),
            Loop(None, (LocalGet(0), i32(1), Binop("i32", "sub"), LocalTee(0), BrIf(0))),
            LocalGet(0),
        )),
        Values((0,)),
    ),
    (
        "if with a type use",
        main((i32(7), i32(0), If(TypeUse(1), (), (Drop(), i32(8))), Br(0)), types=(I32, UNARY)),
        Values((8,)),
    ),
    (
        "narrow signed load of a store",
        main(
            (i32(0), i32(0xFF), Store("i32", AT0, 8), i32(0), Load("i32", AT0, (8, "s"))),
            mems=ONE_PAGE,
        ),
        Values(((1 << 32) - 1,)),
    ),
    ("memory.size", main((MemorySize(),), mems=ONE_PAGE), Values((1,))),
    ("load past the memory", main((i32(65533), Load("i32", AT0, None)), mems=ONE_PAGE), OOB),
    (
        "store past the memory",
        main((i32(0), i32(0), Store("i32", MemArg(0, 65536), None), i32(0)), mems=ONE_PAGE),
        OOB,
    ),
    (
        "indirect through a twice declared type",
        main((i32(0), CallIndirect(0, TypeUse(1))), types=(I32, I32), funcs=(FIVE,), indirect=True),
        Values((5,)),
    ),
    (
        "indirect past the table",
        main((i32(3), CallIndirect(0, TypeUse(0))), funcs=(FIVE,), indirect=True),
        Trap("undefined element"),
    ),
    (
        "indirect to a null element",
        main((i32(1), CallIndirect(0, TypeUse(0))), funcs=(FIVE,), indirect=True),
        Trap("uninitialized element"),
    ),
    (
        "indirect at another type",
        main(
            (i32(0), i32(0), CallIndirect(0, TypeUse(1))),
            types=(I32, UNARY), funcs=(FIVE,), indirect=True,
        ),
        Trap("indirect call type mismatch"),
    ),
    ("tail call", main((ReturnCall(1),), funcs=(FIVE,)), Values((5,))),
    (
        "indirect tail call",
        main((i32(0), ReturnCallIndirect(0, TypeUse(0))), funcs=(FIVE,), indirect=True),
        Values((5,)),
    ),
    ("a zero divisor", main((i32(1), i32(0), Binop("i32", "div_u"))), DIVIDE),
]  # fmt: skip


@pytest.mark.parametrize(("name", "module", "outcome"), CASES, ids=[c[0] for c in CASES])
def test_a_fixed_run(name: str, module: Module, outcome: Outcome) -> None:
    assert invoke(started(module), 0, (), 1000) == outcome, name


def test_a_tail_call_loop_runs_past_the_depth_limit() -> None:
    count_down = (
        LocalGet(0), If("i32", (LocalGet(0), i32(1), Binop("i32", "sub"), ReturnCall(0)), (i32(9),))
    )  # fmt: skip
    instance = started(main(count_down, types=(UNARY,)))
    assert invoke(instance, 0, (10 * DEPTH,), 10**5) == Values((9,))


def test_unbounded_recursion_in_nested_blocks_is_exhausted() -> None:
    body: tuple[Instr, ...] = (Call(0),)
    for _ in range(4):
        body = (Block(None, body),)
    instance = started(main((*body, i32(0))))
    assert invoke(instance, 0, (), 10**6) == Exhausted()


def test_a_run_past_its_budget_is_out_of_steps() -> None:
    assert invoke(started(main((i32(1), i32(2), Drop()))), 0, (), 2) == OutOfSteps()


def test_a_trap_keeps_the_globals_written_before_it() -> None:
    mutable = (Global(GlobalType(mutable=True, type="i32"), (i32(1),)),)
    instance = started(main((i32(7), GlobalSet(0), Unreachable(), GlobalGet(0)), globals_=mutable))
    assert invoke(instance, 0, (), 100) == Trap("unreachable")
    assert instance.globals == [7]


def test_a_data_segment_past_the_memory_traps_at_instantiation() -> None:
    fits = Module(mems=ONE_PAGE, datas=(Data((i32(65535),), b"\x01"),))
    past = Module(mems=ONE_PAGE, datas=(Data((i32(65536),), b"\x01"),))
    assert isinstance(instantiate(fits), Instance)
    assert instantiate(past) == Trap("out of bounds memory access")


def test_an_element_segment_past_the_table_traps_at_instantiation() -> None:
    past = Module(types=(I32,), funcs=(FIVE,), tables=TABLE, elems=(Elem(0, (i32(3),), (0,)),))
    assert instantiate(past) == Trap("out of bounds table access")


@pytest.mark.parametrize(
    "module",
    [
        Module(types=(FuncType((), ()),), funcs=(Func(0, (), ()),), start=0),
        Module(types=(FuncType((), ()),), imports=(Import("m", "f", FuncImport(0)),)),
    ],
)
def test_a_module_with_imports_or_a_start_is_refused(module: Module) -> None:
    with pytest.raises(ValueError, match="closed"):
        instantiate(module)
