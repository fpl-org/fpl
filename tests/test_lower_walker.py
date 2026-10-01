"""Σ_walker's constants are the walker's own functions; readback gives walker values."""

import icontract
import pytest
from hypothesis import given
from hypothesis import strategies as st
from lower_strategies import walker_values

from fpl.ast_core import EFFECTS, Call, Dict, Equal, Listed, Push, Quotation, Value
from fpl.cbpv.check import check
from fpl.cbpv.machine import Closure, Panicked, Returned, Val, run
from fpl.cbpv.sig import FirstOrder
from fpl.cbpv.syntax import (
    App,
    Base,
    Comp,
    Const,
    Dyn,
    Inr,
    Position,
    Prim,
    Program,
    Return,
    Thunk,
    Unit,
    Var,
)
from fpl.errors import FplError, Span
from fpl.eval import BUILTINS, matched
from fpl.lower.walker import (
    CONSTANTS,
    EQ,
    Origin,
    error_line,
    held,
    instance,
    keyed,
    readback,
    signature,
    span,
    stack,
    typed,
)

NUM = Base("Num")
positions = st.none() | st.builds(Position, st.integers(1, 9), st.integers(1, 9))


def no_handler(op: str, _cap: Val, _arg: Val) -> Val:
    raise AssertionError(f"Σ_walker has no operation {op}")


def applied(name: str, args: tuple[Value, ...], at: Position | None) -> Comp:
    """`name` applied to `args`, the deepest first, as the IR pushes a word's inputs."""
    outs = (Dyn(),) * len(EFFECTS[name].outs) if name in EFFECTS else (Dyn(),)
    comp: Comp = Prim(name, instance([typed(a) for a in reversed(args)], outs), frozenset(), at)
    for a in reversed(args):
        comp = App(Const(a, typed(a)), comp)
    return comp


def outcome(comp: Comp, extra: tuple[tuple[str, FirstOrder], ...] = ()) -> tuple[Value, ...] | str:
    (r,) = run(Program((), (comp,)), signature(extra), handler=no_handler)
    if isinstance(r.end, Panicked):
        return error_line(r.end)
    assert isinstance(r.end, Returned)
    return stack(r.end.value)


@given(st.sampled_from(sorted(CONSTANTS)), st.data(), positions)
def test_constants_are_walkers(name: str, data: st.DataObject, at: Position | None) -> None:
    """[law: constants-are-walkers] Every first-order constant of Σ_walker, applied to walker
    values `walker_values()` draws, returns what the walker function it wraps returns (as a
    `Const`), or `Panicked` with the `FplError` that function raises; `readback` of a `Const` is
    its value."""
    n = len(EFFECTS[name].ins)
    args = tuple(data.draw(st.lists(walker_values(), min_size=n, max_size=n)))
    try:
        want: tuple[Value, ...] | str = BUILTINS[name](span(at), *args)
    except FplError as error:
        want = str(error)
    assert outcome(applied(name, args, at)) == want
    assert all(readback(Const(a, typed(a))) == a for a in args)


def test_arguments_reach_the_walker_top_last() -> None:
    one, two = Const(1, NUM), Const(2, NUM)
    minus = Prim("-", instance([NUM, NUM], [NUM]), frozenset(), Position(1, 5))
    program = Program((), (App(one, App(two, minus)),))
    assert check(program, signature(), loops=False) is None
    assert outcome(program.runs[0]) == (-1,)


def test_a_constant_without_a_call_site_panics_at_0_0() -> None:
    assert outcome(applied("?", (), None)) == "ERROR: 0:0 unfilled goal"


def test_held_substitutes_outermost_first() -> None:
    literal = Listed((Quotation((Call("x", Span(1, 1)), Call("y", Span(1, 3)))),))
    got = outcome(applied("held", ("a", 5), None), (("held", held(literal, ("x", "y"))),))
    assert got == (Listed((Quotation((Push(5), Push("a"))),)),)


def test_held_takes_each_name_once() -> None:
    with pytest.raises(icontract.ViolationError):
        held(Listed(()), ("x", "x"))


def test_keyed_puts_the_first_key_deepest() -> None:
    got = outcome(applied("dict", (1, 2), None), (("dict", keyed(("a", "b"))),))
    assert got == (Dict((("a", 1), ("b", 2))),)


def test_readback_refuses_what_is_not_walker_data() -> None:
    assert stack(Unit()) == ()
    with pytest.raises(TypeError):
        readback(Unit())
    with pytest.raises(TypeError):
        readback(Const((1, 2), Dyn()))


def test_readback_fills_a_closure_from_its_environment() -> None:
    """A captured name is looked up past inner bindings; a captured thunk literal reads back as
    its own origin's quotation."""
    at = Span(1, 1)
    outer = Origin(
        (Call("a", at), Call("b", at), Call("c", at)),
        (("a", Var("x")), ("b", Thunk(Return(Unit()), 1)), ("c", Const(3, NUM))),
        0,
        3,
    )
    inner = Origin((Push(1),), (), 0, 1)
    env = ("y", Const(9, NUM), ("x", Const(7, NUM), None))
    got = readback(Closure(Return(Unit()), env, 0), (outer, inner))
    assert got == Quotation((Push(7), Push(Quotation((Push(1),))), Push(3)))


@given(walker_values(), walker_values(), st.booleans())
def test_eq_is_the_walkers_literal_pattern(a: Value, b: Value, same: bool) -> None:
    """`eq` is `inr` exactly where the walker's literal pattern for `a` matches `b`."""
    b = a if same else b
    got = EQ.apply((a, b), None)
    assert isinstance(got, Inr) == (matched(Equal(Push(a)), b, {}) is not None)
