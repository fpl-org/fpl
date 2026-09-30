"""Runnable modules (design section 7): closed modules that end by their own fuel, run in the
evaluator and compared with both engines."""

from hypothesis import given
from hypothesis import strategies as st
from wasm_oracle import Item, Run, Tools, run_wabt, run_wasmtime
from wasm_strategies import MAIN, functypes, operands, runnable_modules, step_bound

from fpl.asm.wasm.exec import Instance, Values, instantiate, invoke
from fpl.asm.wasm.instr import CallIndirect, Const, Instr, ReturnCallIndirect
from fpl.asm.wasm.module import Elem, Export, Func, Module, Table
from fpl.asm.wasm.numerics import Trap
from fpl.asm.wasm.text import print_module
from fpl.asm.wasm.types import FuncType, Limits, TableType, TypeUse
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
    items: list[Item] = [Run(print_module(module), typed)]
    for report in (run_wabt(wasm_tools, items), run_wasmtime(wasm_tools, items)):
        assert report.wrong == (), report.output
