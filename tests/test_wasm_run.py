"""Runnable modules (design section 7): closed modules that end by their own fuel, run in the
evaluator and compared with both engines."""

import pytest
from hypothesis import given
from hypothesis import strategies as st
from wasm_oracle import Calls, Get, Invoke, Item, Run, Tools, run_wabt, run_wasmtime
from wasm_strategies import MAIN, functypes, operands, runnable_modules, step_bound

from fpl.asm.wasm.exec import Instance, Values, instantiate, invoke
from fpl.asm.wasm.instr import (
    Call,
    CallIndirect,
    Const,
    Instr,
    ReturnCall,
    ReturnCallIndirect,
)
from fpl.asm.wasm.module import Elem, Export, Func, Module, Table
from fpl.asm.wasm.numerics import Trap
from fpl.asm.wasm.text import print_module
from fpl.asm.wasm.types import FuncType, Limits, NumType, TableType, TypeUse
from fpl.asm.wasm.valid import check


@given(runnable_modules())
def test_a_runnable_module_ends_within_the_bound_of_its_fuel(module: Module) -> None:
    """[law: fuel-terminates] Every runnable module ends in the evaluator within a step bound
    computed from its fuel K and its size, and never reaches `OutOfSteps` or `Exhausted` under
    that bound.

    The checker runs first, so a guard that breaks typing shows as the checker's error.
    """
    assert check(module) is None
    instance = instantiate(module)
    assert isinstance(instance, Instance), instance
    outcome = invoke(instance, MAIN, (), step_bound(module))
    assert isinstance(outcome, Values | Trap), outcome


@st.composite
def duplicated_calls(draw: st.DrawFn) -> tuple[Module, tuple[int, ...]]:
    """A module whose `main` calls through its table, by `call_indirect` or its tail form, a
    function declared with one of two type indices of the same FuncType, naming the other; and
    the constants that function returns."""
    t = draw(functypes)
    declared, named = draw(st.permutations((1, 2)))
    results = tuple(draw(operands(r)) for r in t.results)
    args = tuple(Const(p, draw(operands(p))) for p in t.params)
    use = TypeUse(named)
    calls: tuple[Instr, ...] = (CallIndirect(0, use), ReturnCallIndirect(0, use))
    call = draw(st.sampled_from(calls))
    main = Func(0, (), (*args, Const("i32", 0), call))
    callee = Func(declared, (), tuple(map(Const, t.results, results)))
    module = Module(
        types=(FuncType((), t.results), t, t),
        tables=(Table(TableType(Limits(1, 1))),),
        funcs=(main, callee),
        elems=(Elem(0, (Const("i32", 0),), (1,)),),
        exports=(Export("main", "func", 0),),
    )
    return module, results


@given(duplicated_calls())
def test_an_indirect_call_through_a_duplicate_type_calls_the_function(
    wasm_tools: Tools, case: tuple[Module, tuple[int, ...]]
) -> None:
    """[law: types-structural] `call_indirect` through a type index declared twice with the same
    `FuncType` calls the function instead of trapping, in the evaluator and in both engines."""
    module, results = case
    assert check(module) is None
    instance = instantiate(module)
    assert isinstance(instance, Instance), instance
    assert invoke(instance, 0, (), 16) == Values(results)
    typed = tuple(zip(module.types[0].results, results, strict=True))
    agree(wasm_tools, [Run(print_module(module), typed)])


def test_a_tail_call_drops_the_operands_under_its_arguments(wasm_tools: Tools) -> None:
    """`return_call` ends its caller, whose operands under the call's arguments go with it
    (3.4.2, 4.4.8): `main` pushes 5 and calls a function that pushes 9, then tail-calls one
    returning 1, so `main` returns (5, 1) in the evaluator and wasmtime.

    wabt 1.0.41's spectest-interp keeps the 9 and returns (9, 1). The wabt leg asserts that
    wrong answer, so a wabt that fixes it fails here, and hole wabt-tail-call-operands closes.
    """
    types = (FuncType((), ("i32", "i32")), FuncType((), ("i32",)))
    module = Module(
        types=types,
        funcs=(
            Func(0, (), (Const("i32", 5), Call(1))),
            Func(1, (), (Const("i32", 9), ReturnCall(2))),
            Func(1, (), (Const("i32", 1),)),
        ),
        exports=(Export("main", "func", 0),),
    )
    assert check(module) is None
    instance = instantiate(module)
    assert isinstance(instance, Instance), instance
    assert invoke(instance, 0, (), 16) == Values((5, 1))
    item = Run(print_module(module), (("i32", 5), ("i32", 1)))
    assert run_wasmtime(wasm_tools, [item]).wrong == ()
    assert run_wabt(wasm_tools, [item]).wrong == (0,)


def agree(tools: Tools, items: list[Item]) -> None:
    """Both engines pass every item."""
    for report in (run_wabt(tools, items), run_wasmtime(tools, items)):
        assert report.wrong == (), report.output


def expected(module: Module) -> Calls:
    """The runnable `module` printed, with `main`'s results or trap kind in the evaluator, then
    the value each exported global holds after it, the fuel included."""
    instance = instantiate(module)
    assert isinstance(instance, Instance), instance
    results = module.types[module.funcs[MAIN].type].results
    expect: tuple[tuple[NumType, int], ...] | str
    match invoke(instance, MAIN, (), step_bound(module)):
        case Values(values):
            expect = tuple(zip(results, values, strict=True))
        case Trap(kind):
            expect = kind
        case outcome:
            pytest.fail(f"{outcome} within the bound of the fuel")
    reads = tuple(
        Get(e.name, (module.globals[e.index].type.type, instance.globals[e.index]))
        for e in module.exports
        if e.kind == "global"
    )
    return Calls(print_module(module), (Invoke("main", (), expect), *reads))


@given(st.lists(runnable_modules(), min_size=1, max_size=8))
def test_every_runnable_module_runs_alike_in_the_evaluator_and_both_engines(
    wasm_tools: Tools, modules: list[Module]
) -> None:
    """[law: evaluator-agrees] For every runnable module, `main`'s results or trap kind, then
    every exported global (fuel included), are the same in the evaluator, wasmtime and wabt's
    interpreter (done-when 3).

    One batch of up to eight modules per example, each a module and its directives.
    """
    agree(wasm_tools, list(map(expected, modules)))
