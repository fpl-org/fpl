"""Runnable modules (design section 7): closed modules that end by their own fuel, run in the
evaluator and compared with both engines."""

from hypothesis import given
from wasm_strategies import MAIN, runnable_modules, step_bound

from fpl.asm.wasm.exec import Instance, Values, instantiate, invoke
from fpl.asm.wasm.module import Module
from fpl.asm.wasm.numerics import Trap
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
