"""Walker values and walker programs for the lowering's properties (design section 7)."""

from collections.abc import Callable, Mapping
from decimal import Decimal
from functools import partial

from hypothesis import strategies as st

from fpl.ast_core import (
    Bind,
    Call,
    Define,
    Dict,
    Effect,
    Keyed,
    Listed,
    Node,
    Push,
    Quotation,
    Run,
    Statement,
    Strand,
    Symbol,
    Value,
)
from fpl.desugar import desugar, resugar
from fpl.errors import Span
from fpl.parse import parse
from fpl.print import render
from fpl.types import ARROWS, Arrow, Input, Kind, Sort, elaborate, sort

NAMES = st.sampled_from(("a", "b", "k", "dup", "x"))
atoms: st.SearchStrategy[int | Decimal | str] = st.one_of(
    st.integers(-5, 5),
    st.decimals(-5, 5, places=1, allow_nan=False, allow_infinity=False),
    st.text("xyz", max_size=2),
)


def _compound(children: st.SearchStrategy[Value]) -> st.SearchStrategy[Value]:
    code = st.lists(st.one_of(children.map(Push), NAMES.map(lambda n: Call(n, Span(1, 1)))))
    return st.one_of(
        st.lists(children, max_size=3).map(lambda xs: Listed(tuple(xs))),
        code.map(lambda c: Quotation(tuple(c))),
        st.lists(st.tuples(NAMES, children), max_size=2).map(lambda es: Dict(tuple(es))),
    )


def walker_values() -> st.SearchStrategy[Value]:
    """Walker values at every sort: atoms, strands, symbols, and lists, quotations and dicts
    holding any of them."""
    leaves = st.one_of(
        atoms,
        st.lists(atoms, min_size=2, max_size=3).map(lambda xs: Strand(tuple(xs))),
        NAMES.map(Symbol),
    )
    return st.recursive(leaves, _compound, max_leaves=6)


START = Span(1, 1)
BINDERS = ("a", "b", "c")  # no word or builtin is spelled so
WORDS = ("f", "g")
KEYS = ("k", "m")
FIRST_ORDER = ("+", "-", "times", "swap", "dup", "drop", "enclose", "pair", "cons")
digits = st.one_of(
    st.integers(0, 9), st.integers(0, 99).map(lambda n: Decimal(f"{n // 10}.{n % 10}"))
)
plain = st.one_of(digits, st.text("xyz", min_size=1, max_size=2))
type Draw = st.DrawFn
type Stack = tuple[Sort, ...]
type Env = Mapping[str, Sort]
type Moved = tuple[tuple[Node, ...], Stack]


def _held(env: Env) -> st.SearchStrategy[Value]:
    """A literal that may mention the binders in scope: a list holding quotations."""
    calls = [Call(n, START) for n in env]
    code = st.one_of(plain.map(Push), *([st.sampled_from(calls)] if calls else []))
    quotation = code.map(lambda node: Quotation((node,)))
    strand = st.lists(st.integers(0, 9), min_size=2, max_size=3).map(lambda xs: Strand(tuple(xs)))
    items = st.lists(st.one_of(plain, quotation), max_size=3)
    symbols = st.sampled_from(("a", "k")).map(Symbol)
    return st.one_of(plain, strand, symbols, items.map(lambda xs: Listed(tuple(xs))))


def _fits(arrow: Arrow, stack: Stack) -> bool:
    """The arrow's inputs are there and elaboration's `met` takes them: a number is wanted
    where no text or symbol is known."""
    cut = len(stack) - len(arrow.ins)
    wrong = (Kind.TEXT, Kind.SYMBOL)
    met = zip(arrow.ins, stack[cut:], strict=True)
    return cut >= 0 and not any(need == Kind.NUMBER and have in wrong for need, have in met)


def _applied(arrow: Arrow, stack: Stack) -> Stack:
    cut = len(stack) - len(arrow.ins)
    outs = (stack[cut + s.index] if isinstance(s, Input) else s for s in arrow.outs)
    return (*stack[:cut], *outs)


def _push(draw: Draw, stack: Stack, env: Env) -> Moved:
    value = draw(_held(env))
    return (Push(value),), (*stack, sort(value))


def _call(name: str, arrow: Arrow, _draw: Draw, stack: Stack, _env: Env) -> Moved:
    return (Call(name, START),), _applied(arrow, stack)


def _binder(name: str, _draw: Draw, stack: Stack, env: Env) -> Moved:
    return (Call(name, START),), (*stack, env[name])


def _keyed(draw: Draw, stack: Stack, env: Env) -> Moved:
    keys = draw(st.lists(st.sampled_from(KEYS), min_size=1, max_size=2, unique=True))
    calls = [Call(n, START) for n in env]
    node = st.one_of(plain.map(Push), *([st.sampled_from(calls)] if calls else []))
    return (Keyed(tuple((k, draw(node)) for k in keys), START),), (*stack, Kind.VALUE)


def _moves(arrows: Mapping[str, Arrow], stack: Stack, env: Env) -> list[Callable[..., Moved]]:
    """Every step the code may take next without an elaboration error."""
    moves: list[Callable[..., Moved]] = [_push, _keyed, *(partial(_binder, n) for n in env)]
    moves += [partial(_call, n, a) for n, a in arrows.items() if _fits(a, stack)]
    return moves


def _code(draw: Draw, arrows: Mapping[str, Arrow], start: Stack, env: Env, steps: int) -> Moved:
    """`steps` nodes over the static stack of sorts `start`; a binder takes the rest as its
    scope."""
    nodes: list[Node] = []
    stack = start
    for left in range(steps, 0, -1):
        if stack and draw(st.integers(0, 4)) == 0:
            name = draw(st.sampled_from(BINDERS))
            body, stack = _code(draw, arrows, stack[:-1], {**env, name: stack[-1]}, left - 1)
            nodes.append(Bind(name, body, START))
            break
        more, stack = draw(st.sampled_from(_moves(arrows, stack, env)))(draw, stack, env)
        nodes.extend(more)
    return tuple(nodes), stack


def _define(draw: Draw, name: str, arrows: Mapping[str, Arrow]) -> Define:
    n = draw(st.integers(0, 2))
    code, stack = _code(draw, arrows, tuple(map(Input, range(n))), {}, draw(st.integers(0, 4)))
    ins = tuple(f"i{k}" for k in range(n))
    return Define(name, Effect(ins, tuple(f"o{k}" for k in range(len(stack)))), code)


def source_of(statements: tuple[Statement, ...]) -> str:
    """The source `resugar` writes for core, which must desugar back to it and elaborate."""
    source = render(resugar(statements))
    assert desugar(parse(source)) == statements, source
    elaborate(statements)
    return source


@st.composite
def straight(draw: Draw) -> str:
    """Straight-line programs as source: literals, lists holding quotations that call binders in
    scope, symbols, dicts, first-order builtins at sorts `met` takes, binders named off every
    word and builtin, queries, and words calling earlier words (design section 7). Run-time
    errors are drawn; elaboration errors are not."""
    arrows = {n: ARROWS[n] for n in FIRST_ORDER}
    statements: list[Statement] = []
    for name in WORDS[: draw(st.integers(0, 2))]:
        statements.append(_define(draw, name, arrows))
        known = elaborate(tuple(statements))[0]
        arrows |= {k: known[k] for k in (name, f"{name}/doc", f"{name}/effect")}
    for _ in range(draw(st.integers(1, 3))):
        statements.append(Run(_code(draw, arrows, (), {}, draw(st.integers(1, 5)))[0]))
    return source_of(tuple(statements))
