"""Σ_walker: the walker's sorts as base types and its own functions as constants (design 6.2).

Promised: a first-order constant applies the walker function it wraps to the walker values it
receives and returns what that function returns, one result as a `Const` at its sort's type,
several as a right-nested `Pair`, none as `Unit`; the `FplError` the function raises becomes
the constant's `Panic`, so a run ends with the walker's own error line (hole panics). Arguments
reach a constant top of stack first (`fpl.cbpv.sig`), the walker's builtins take the top last,
so the arguments are handed over reversed. `,` is no constant (code as data is refused before
the lowering, hole level-one) and neither is `_` (it lowers to nothing). The semantics is
borrowed, not restated (hole walker-constants).

`held(literal, names)` is the constant for one pushed list or quotation that mentions binders in
scope: it takes their values, outermost binder first, and substitutes each as the walker's
`Bind` step does. `keyed(keys)` builds a dict from one value per key, the first key deepest.

`box(origins)` turns a closure into the walker quotation it stands for, where a thunk meets a
position that takes walker data; `control(w)` is the walker's control word `w` for an operand
statically not a quotation, which the walker refuses before it runs any code.

Readback: a `Const` is its walker value; a closure is its origin's quotation with each binder it
closes over substituted, outermost first, by the readback of its value (`fpl.eval.substitute`,
as the walker's `Bind` steps do); a run's result is its final static stack, returned as a tuple
(`Unit`, one value, or a right-nested pair) and read back item by item.
"""

from collections.abc import Callable, Hashable, Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal

import icontract

from fpl.ast_core import EFFECTS, Dict, Listed, Node, Quotation, Strand, Symbol, Value
from fpl.cbpv.machine import Closure, Env, Panicked, Val, VPair
from fpl.cbpv.sig import FirstOrder, Panic, Signature
from fpl.cbpv.syntax import (
    Arrow,
    Base,
    Const,
    CType,
    Dyn,
    F,
    One,
    Pair,
    Position,
    Prim,
    Prod,
    Thunk,
    U,
    Unit,
    Var,
    VType,
)
from fpl.cbpv.syntax import Value as IRValue
from fpl.errors import FplError, Span
from fpl.eval import BUILTINS, CONTROLS, substitute
from fpl.eval import held as substituted
from fpl.types import Kind, sort

SORTS: dict[Kind, VType] = {
    Kind.NUMBER: Base("Num"),
    Kind.TEXT: Base("Text"),
    Kind.SYMBOL: Base("Sym"),
    Kind.VALUE: Dyn(),
}
BASES = frozenset({"Num", "Text", "Sym"})
UNLOWERED = frozenset({",", "_"})
WALKER = (int, Decimal, str, Strand, Listed, Quotation, Symbol, Dict)


def typed(value: Value) -> VType:
    """The IR type of a walker value: its sort's base type, `Dyn` for an untracked one."""
    sorted_ = sort(value)
    return SORTS[sorted_] if isinstance(sorted_, Kind) else Dyn()


def packed(values: Sequence[Value]) -> IRValue:
    """Walker results as one IR value, each a `Const` of its sort's type (`paired`)."""
    return paired([Const(v, typed(v)) for v in values])


def paired(items: Sequence[IRValue]) -> IRValue:
    """Values as one: none as `Unit`, one as itself, several as a right-nested pair, the first
    outermost."""
    if not items:
        return Unit()
    tail = items[-1]
    for item in reversed(items[:-1]):
        tail = Pair(item, tail)
    return tail


def product(types: Sequence[VType]) -> VType:
    """The type `packed` gives values of these types."""
    if not types:
        return One()
    tail = types[-1]
    for t in reversed(types[:-1]):
        tail = Prod(t, tail)
    return tail


def results(t: CType) -> tuple[VType, ...]:
    """The values a computation of type `t` returns, as `instance` packs them."""
    if isinstance(t, Arrow):
        return results(t.res)
    assert isinstance(t, F), t
    return unpacked(t.value)


def unpacked(t: VType) -> tuple[VType, ...]:
    """The types `product` packed."""
    if isinstance(t, One):
        return ()
    return (t.left, *unpacked(t.right)) if isinstance(t, Prod) else (t,)


def instance(ins: Sequence[VType], outs: Sequence[VType]) -> CType:
    """A constant's instance type: `ins` popped top first, then `F` of its results."""
    comp: CType = F(product(outs))
    for t in reversed(ins):
        comp = Arrow(t, comp)
    return comp


def span(at: Position | None) -> Span:
    """The walker's span for a call site; a constant with none reports 0:0."""
    return Span(at.line, at.col) if at else Span(0, 0)


def wrapped(arity: int, walker: Callable[..., tuple[Value, ...]]) -> FirstOrder:
    """A constant applying `walker(span, *args)` to its arguments, the top last."""

    def apply(args: tuple[Hashable, ...], at: Position | None) -> IRValue | Panic:
        try:
            return packed(walker(span(at), *reversed(args)))
        except FplError as error:
            return Panic(error)

    return FirstOrder(arity, apply)


CONSTANTS: dict[str, FirstOrder] = {
    name: wrapped(len(EFFECTS[name].ins), fn)
    for name, fn in BUILTINS.items()
    if name not in UNLOWERED
}


def distinct(names: Sequence[str]) -> bool:
    """No name twice: a shadowed binder is not captured, only the innermost of a name is."""
    return len(set(names)) == len(names)


@icontract.require(distinct)
def held(literal: Value, names: Sequence[str]) -> FirstOrder:
    """The constant for `literal` with `names` in scope, outermost first: it takes their values
    (the outermost the top) and substitutes each in turn, as the walker's binders do."""

    def fill(_span: Span, *values: Value) -> tuple[Value, ...]:
        inner = literal
        for name, value in zip(names, reversed(values), strict=True):
            inner = substituted(inner, name, value)
        return (inner,)

    return wrapped(len(names), fill)


def keyed(keys: Sequence[str]) -> FirstOrder:
    """The constant building a dict of one value per key, the last key the top."""

    def build(_span: Span, *values: Value) -> tuple[Value, ...]:
        return (Dict(tuple(zip(keys, values, strict=True))),)

    return wrapped(len(keys), build)


def control(word: str) -> FirstOrder:
    """The control word `word` on an operand statically not a quotation: the walker's own
    function, which refuses it (`quoted` runs before any other check in every control word)."""

    def refuse(span: Span, *args: Value) -> tuple[Value, ...]:
        CONTROLS[word](span, {}, *args)
        raise AssertionError(word)  # pragma: no cover -- quoted() refuses first

    return wrapped(len(EFFECTS[word].ins), refuse)


@dataclass(frozen=True)
class Origin:
    """A literal quotation's code, the binders in scope where it is pushed (each walker name,
    outermost first, with the IR value of its innermost binding), and the counts of values its
    body takes and leaves as pass 2 computed them."""

    code: tuple[Node, ...]
    names: tuple[tuple[str, IRValue], ...]
    ins: int
    outs: int


def box(origins: Sequence[Origin]) -> FirstOrder:
    """The constant turning a closure into its walker quotation (walker data, `Dyn`)."""

    def apply(args: tuple[Hashable, ...], _at: Position | None) -> IRValue:
        return packed([readback(args[0], origins)])

    return FirstOrder(1, apply)


def boxes(p: Prim) -> bool:
    """`box` at a thunk: the one constant whose input is not walker data."""
    ins = inputs(p.type)
    return p.name == "box" and len(ins) == 1 and isinstance(ins[0], U)


def signature(extra: Iterable[tuple[str, FirstOrder]] = ()) -> Signature:
    """Σ_walker with a program's own `held` and `keyed` constants: an instance is admitted when
    its constant is known, takes as many values as it declares, and every input is walker data."""
    constants = {**CONSTANTS, **dict(extra)}

    def admits(p: Prim) -> bool:
        ins = inputs(p.type)
        known = p.name in constants and len(ins) == constants[p.name].arity
        return known and (all(isinstance(t, Dyn | Base) for t in ins) or boxes(p))

    return Signature(BASES, constants, admits, {}, Dyn())


def inputs(t: CType) -> tuple[VType, ...]:
    """The values a computation of type `t` pops, in order."""
    return (t.arg, *inputs(t.res)) if isinstance(t, Arrow) else ()


def readback(value: object, origins: Sequence[Origin] = ()) -> Value:
    """The walker value an IR value stands for: a constant is its value, a closure its origin's
    quotation with the binders it closes over substituted."""
    if isinstance(value, Closure) and value.origin is not None:
        origin = origins[value.origin]
        code = origin.code
        for name, bound in origin.names:
            code = substitute(code, name, readback(resolved(bound, value.env), origins))
        return Quotation(code)
    if not isinstance(value, Const) or not isinstance(value.value, WALKER):
        raise TypeError(f"no walker value for {value!r}")
    return value.value


def resolved(value: IRValue, env: Env) -> Val:
    """An entry's IR value in a closure's environment: a name its binding, a thunk literal a
    closure over that environment."""
    if isinstance(value, Var):
        while env is not None and env[0] != value.name:
            env = env[2]
        assert env is not None, value
        return env[1]
    if isinstance(value, Thunk):
        return Closure(value.body, env, value.origin)
    assert isinstance(value, Const), value
    return value


def stack(value: Val, origins: Sequence[Origin] = ()) -> tuple[Value, ...]:
    """A run's result, the tuple of its final static stack, as walker values."""
    if isinstance(value, VPair):
        return (readback(value.left, origins), *stack(value.right, origins))
    return () if isinstance(value, Unit) else (readback(value, origins),)


def error_line(end: Panicked) -> str:
    """The line the walker prints for the error a constant panicked with."""
    return str(end.payload)
