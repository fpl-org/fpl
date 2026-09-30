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

Readback: a `Const` is its walker value; a run's result is its final static stack, returned as
a tuple (`Unit`, one value, or a right-nested pair) and read back item by item. A closure is
refused by readback until quotations lower.
"""

from collections.abc import Callable, Hashable, Iterable, Sequence
from decimal import Decimal

import icontract

from fpl.ast_core import EFFECTS, Dict, Listed, Quotation, Strand, Symbol, Value
from fpl.cbpv.machine import Panicked, Val, VPair
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
    Unit,
    VType,
)
from fpl.cbpv.syntax import Value as IRValue
from fpl.errors import FplError, Span
from fpl.eval import BUILTINS
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
    """Results as one IR value: none as `Unit`, one as itself, several as a right-nested pair."""
    consts = [Const(v, typed(v)) for v in values]
    if not consts:
        return Unit()
    tail: IRValue = consts[-1]
    for c in reversed(consts[:-1]):
        tail = Pair(c, tail)
    return tail


def product(types: Sequence[VType]) -> VType:
    """The type `packed` gives values of these types."""
    if not types:
        return One()
    tail = types[-1]
    for t in reversed(types[:-1]):
        tail = Prod(t, tail)
    return tail


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


def signature(extra: Iterable[tuple[str, FirstOrder]] = ()) -> Signature:
    """Σ_walker with a program's own `held` and `keyed` constants: an instance is admitted when
    its constant is known, takes as many values as it declares, and every input is walker data."""
    constants = {**CONSTANTS, **dict(extra)}

    def admits(p: Prim) -> bool:
        ins = inputs(p.type)
        known = p.name in constants and len(ins) == constants[p.name].arity
        return known and all(isinstance(t, Dyn | Base) for t in ins)

    return Signature(BASES, constants, admits, {}, Dyn())


def inputs(t: CType) -> tuple[VType, ...]:
    """The values a computation of type `t` pops, in order."""
    return (t.arg, *inputs(t.res)) if isinstance(t, Arrow) else ()


def readback(value: Val) -> Value:
    """The walker value an IR value stands for: a constant is its value."""
    if not isinstance(value, Const) or not isinstance(value.value, WALKER):
        raise TypeError(f"no walker value for {value!r}")
    return value.value


def stack(value: Val) -> tuple[Value, ...]:
    """A run's result, the tuple of its final static stack, as walker values."""
    if isinstance(value, VPair):
        return (readback(value.left), *stack(value.right))
    return () if isinstance(value, Unit) else (readback(value),)


def error_line(end: Panicked) -> str:
    """The line the walker prints for the error a constant panicked with."""
    return str(end.payload)
