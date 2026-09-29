"""Elaboration over the core AST: each word's effect inferred from its body and checked against
its effect line, before any line runs.

A sort is what elaboration knows of a value: a number, a text, a symbol, or a value of no sort
it tracks (a list, a quotation, a dict, what a control word leaves: trusted, hole typed-fragment).
While a body is inferred, the values it takes are inputs whose sorts are not known yet; arithmetic
on one makes it a number. An arrow is a word's inferred effect: the sorts it takes and leaves.
"""

from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import Enum
from typing import assert_never

from fpl.ast_core import (
    EFFECTS,
    Bind,
    Call,
    Define,
    Keyed,
    Match,
    Node,
    Push,
    Run,
    Statement,
    Strand,
    Symbol,
    Value,
)
from fpl.errors import FplError, Span
from fpl.eval import CONTROLS


@dataclass(frozen=True)
class Input:
    """The index-th value a word takes, its sort not known yet."""

    index: int


class Kind(Enum):
    """A sort of value elaboration tracks; VALUE is one of no sort it tracks."""

    NUMBER = "number"
    TEXT = "text"
    SYMBOL = "symbol"
    VALUE = "value"


type Sort = Kind | Input


@dataclass(frozen=True)
class Arrow:
    """A word's effect: the sorts it takes, then those it leaves; an Input in `outs` is the value
    taken at that index."""

    ins: tuple[Sort, ...]
    outs: tuple[Sort, ...]


@dataclass(frozen=True)
class Typing:
    """What elaboration knows at a point in the code: the sorts on the stack, top last; the sort
    each bound name stands for; the sorts the body's inputs have been found to be."""

    stack: tuple[Sort, ...]
    env: Mapping[str, Sort]
    known: Mapping[int, Sort]


class UntypedError(Exception):
    """Code outside what elaboration infers (a match, a control word, whose effect is the code it
    runs): its word's effect line is trusted."""


NUMBERS = Arrow((Kind.NUMBER, Kind.NUMBER), (Kind.NUMBER,))
ARROWS: dict[str, Arrow] = {
    **{
        name: Arrow(tuple(map(Input, range(len(e.ins)))), (Kind.VALUE,) * len(e.outs))
        for name, e in EFFECTS.items()
        if name not in CONTROLS
    },
    "+": NUMBERS,
    "-": NUMBERS,
    "times": NUMBERS,
    "swap": Arrow((Input(0), Input(1)), (Input(1), Input(0))),
    "dup": Arrow((Input(0),), (Input(0), Input(0))),
    "drop": Arrow((Input(0),), ()),
}
QUERIES = ("history", "doc", "effect")


def elaborate(statements: tuple[Statement, ...]) -> dict[str, Arrow]:
    """Every word's arrow, builtins and queries too. A body that leaves another count than its
    effect line promises is refused at its definition, and a sort a word cannot take, in a body
    or a line, at the word. A word called before its last definition is inferred meets that
    definition's effect line."""
    arrows = words([s for s in statements if isinstance(s, Define)])
    for s in statements:
        if isinstance(s, Run):
            with suppress(UntypedError):
                after(Typing((), {}, {}), s.code, arrows)
    return arrows


def words(defines: list[Define]) -> dict[str, Arrow]:
    """Each word's arrow: the one inferred from its last definition, every body checked."""
    arrows = dict(ARROWS)
    for d in defines:
        arrows[d.name] = declared(d)
        arrows.update({f"{d.name}/{query}": Arrow((), (Kind.VALUE,)) for query in QUERIES})
    last = {d.name: d for d in defines}
    for d in defines:
        arrow = inferred(d, arrows)
        if last[d.name] is d:
            arrows[d.name] = arrow
    return arrows


def declared(define: Define) -> Arrow:
    """The effect line as an arrow: any values in, values of no known sort out."""
    ins = tuple(map(Input, range(len(define.effect.ins))))
    return Arrow(ins, (Kind.VALUE,) * len(define.effect.outs))


def inferred(define: Define, arrows: Mapping[str, Arrow]) -> Arrow:
    """The arrow of the body, its inputs as general as the body lets them be; the effect line's
    if the body is untyped."""
    start = Typing(tuple(map(Input, range(len(define.effect.ins)))), {}, {})
    try:
        end = after(start, define.code, arrows)
    except UntypedError:
        return declared(define)
    if len(end.stack) != len(define.effect.outs):
        message = f"leaves {len(end.stack)} values, its effect line {len(define.effect.outs)}"
        raise FplError(define.span, f"{define.name} {message}")
    return Arrow(resolved(start.stack, end), resolved(end.stack, end))


def resolved(sorts: tuple[Sort, ...], typing: Typing) -> tuple[Sort, ...]:
    """The sorts with each input found to be of a sort replaced by it."""
    return tuple(known(s, typing) for s in sorts)


def known(s: Sort, typing: Typing) -> Sort:
    """An input's sort once found, else the sort itself."""
    return typing.known.get(s.index, s) if isinstance(s, Input) else s


def after(typing: Typing, code: tuple[Node, ...], arrows: Mapping[str, Arrow]) -> Typing:
    """What is known once the code has run; a node that cannot is refused at its span."""
    for node in code:
        typing = through(typing, node, arrows)
    return typing


def through(typing: Typing, node: Node, arrows: Mapping[str, Arrow]) -> Typing:
    """What is known once one node has run."""
    match node:
        case Push():
            return replace(typing, stack=(*typing.stack, sort(node.value)))
        case Keyed():
            return replace(typing, stack=(*typing.stack, Kind.VALUE))
        case Bind():
            return bound(typing, node, arrows)
        case Call():
            return called(typing, node, arrows)
        case Match():
            raise UntypedError
        case _:
            assert_never(node)


def bound(typing: Typing, node: Bind, arrows: Mapping[str, Arrow]) -> Typing:
    """The top taken and named for the binder's scope, which runs; the name dies with it."""
    if not typing.stack:
        raise FplError(node.span, "stack underflow")
    env = {**typing.env, node.name: typing.stack[-1]}
    end = after(Typing(typing.stack[:-1], env, typing.known), node.body, arrows)
    return replace(end, env=typing.env)


def called(typing: Typing, node: Call, arrows: Mapping[str, Arrow]) -> Typing:
    """A bound name pushes the sort it stands for; a word takes and leaves its arrow's sorts."""
    if node.name in typing.env:
        return replace(typing, stack=(*typing.stack, typing.env[node.name]))
    if node.name not in arrows:
        raise UntypedError
    return applied(typing, arrows[node.name], node.span)


def applied(typing: Typing, arrow: Arrow, span: Span) -> Typing:
    """The arrow's inputs met by the values under the top, its outputs in their place."""
    cut = len(typing.stack) - len(arrow.ins)
    if cut < 0:
        raise FplError(span, "stack underflow")
    local: dict[int, Sort] = {}
    found = dict(typing.known)
    for need, have in zip(arrow.ins, typing.stack[cut:], strict=True):
        met(need, known(have, typing), local, found, span)
    outs = tuple(local[s.index] if isinstance(s, Input) else s for s in arrow.outs)
    return Typing((*typing.stack[:cut], *outs), typing.env, found)


def met(need: Sort, have: Sort, local: dict[int, Sort], found: dict[int, Sort], span: Span) -> None:
    """One input met: a general one takes the value's sort, a number wants one; an input of the
    body met by a number is found to be one."""
    match need:
        case Input():
            local[need.index] = have
        case _ if isinstance(have, Input):
            found[have.index] = need
        case _ if have not in (need, Kind.VALUE):
            raise FplError(span, "arithmetic on a non-number")
        case _:
            pass


def sort(value: Value) -> Sort:
    """The sort of a value: a strand has its items' sort when they share one."""
    match value:
        case int() | Decimal():
            return Kind.NUMBER
        case str():
            return Kind.TEXT
        case Symbol():
            return Kind.SYMBOL
        case Strand():
            sorts = set(map(sort, value.items))
            return sorts.pop() if len(sorts) == 1 else Kind.VALUE
        case _:
            return Kind.VALUE
