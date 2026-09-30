"""Walker values and walker programs for the lowering's properties (design section 7)."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from functools import partial

from hypothesis import assume
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


@dataclass(frozen=True)
class Quoted:
    """A literal quotation on the drawn stack: the values its body takes and what it leaves."""

    ins: int
    outs: "tuple[Sort | Quoted, ...]"


type Stack = tuple[Sort | Quoted, ...]
type Env = Mapping[str, Sort | Quoted]
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


def _applied(arrow: Arrow | Quoted, stack: Stack) -> Stack:
    cut = len(stack) - (arrow.ins if isinstance(arrow, Quoted) else len(arrow.ins))
    outs = (stack[cut + s.index] if isinstance(s, Input) else s for s in arrow.outs)
    return (*stack[:cut], *outs)


def _push(draw: Draw, stack: Stack, env: Env) -> Moved:
    value = draw(_held(env))
    return (Push(value),), (*stack, sort(value))


def _call(name: str, arrow: Arrow, _draw: Draw, stack: Stack, _env: Env) -> Moved:
    """A builtin or word: a quotation it passes through comes back as walker data (boxed)."""
    after = _applied(arrow, stack)
    cut = len(stack) - len(arrow.ins)
    return (Call(name, START),), (*after[:cut], *(_data(s) for s in after[cut:]))


def _data(s: Sort | Quoted) -> Sort:
    return Kind.VALUE if isinstance(s, Quoted) else s


def _binder(name: str, _draw: Draw, stack: Stack, env: Env) -> Moved:
    return (Call(name, START),), (*stack, env[name])


def _keyed(draw: Draw, stack: Stack, env: Env) -> Moved:
    keys = draw(st.lists(st.sampled_from(KEYS), min_size=1, max_size=2, unique=True))
    calls = [Call(n, START) for n in env]
    node = st.one_of(plain.map(Push), *([st.sampled_from(calls)] if calls else []))
    return (Keyed(tuple((k, draw(node)) for k in keys), START),), (*stack, Kind.VALUE)


def _quote(arrows: Mapping[str, Arrow], draw: Draw, stack: Stack, env: Env) -> Moved:
    """A literal quotation whose body takes up to two inputs and may name the binders in scope."""
    n = draw(st.integers(0, 2))
    code, left = _code(draw, arrows, tuple(map(Input, range(n))), env, draw(st.integers(0, 3)))
    return (Push(Quotation(code)),), (*stack, Quoted(n, left))


def _bang(draw: Draw, stack: Stack, _env: Env) -> Moved:
    """The quotation on top run in place: `!`, or `swap-args` on the two values below it."""
    quoted = stack[-1]
    assert isinstance(quoted, Quoted)
    below = stack[:-1]
    if len(below) >= max(quoted.ins, 2) and draw(st.booleans()):
        return (Call("swap-args", START),), _applied(quoted, (*below[:-2], below[-1], below[-2]))
    return (Call("!", START),), _applied(quoted, below)


def _moves(arrows: Mapping[str, Arrow], stack: Stack, env: Env) -> list[Callable[..., Moved]]:
    """Every step the code may take next without an elaboration error; quotations only where
    `arrows` offers `!`."""
    moves: list[Callable[..., Moved]] = [_push, _keyed, *(partial(_binder, n) for n in env)]
    moves += [partial(_call, n, a) for n, a in arrows.items() if n != "!" and _fits(a, stack)]
    if "!" in arrows:
        moves.append(partial(_quote, arrows))
        top = stack[-1] if stack else None
        if isinstance(top, Quoted) and len(stack) > top.ins:
            moves.append(_bang)
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


@st.composite
def controlled(draw: Draw) -> str:
    """Programs as `straight` draws them, whose run lines also push literal quotations (their
    bodies naming binders in scope) and run them in place with `!` and `swap-args` on stacks
    deep enough; every draw's first line opens with a quotation (design section 7). Nothing a
    refusal kind names is drawn: no quotation reaches `!` as walker data or underflows."""
    # "!" is no arrow of 07's: its key only switches the quotation moves on in `_moves`
    arrows = {n: ARROWS[n] for n in FIRST_ORDER} | {"!": ARROWS["drop"]}
    words = {n: ARROWS[n] for n in FIRST_ORDER}
    statements: list[Statement] = []
    for name in WORDS[: draw(st.integers(0, 2))]:
        statements.append(_define(draw, name, words))
        known = elaborate(tuple(statements))[0]
        added = {k: known[k] for k in (name, f"{name}/doc", f"{name}/effect")}
        arrows |= added
        words |= added
    first, stack = _quote(arrows, draw, (), {})
    rest = _code(draw, arrows, stack, {}, draw(st.integers(0, 4)))[0]
    statements.append(Run((*first, *rest)))
    for _ in range(draw(st.integers(0, 2))):
        statements.append(Run(_code(draw, arrows, (), {}, draw(st.integers(1, 5)))[0]))
    # resugar writes a quotation body such as `0 | 0` as a frame that parses otherwise
    assume(desugar(parse(render(resugar(tuple(statements))))) == tuple(statements))
    return source_of(tuple(statements))
