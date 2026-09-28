"""The core as a step machine: a state is the stack and the code still to run, and `step` runs
one node of it. Over the core AST only."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import assert_never

import icontract

from fpl.ast_core import (
    EFFECTS,
    Call,
    Define,
    Listed,
    Node,
    Number,
    Push,
    Quotation,
    Run,
    Statement,
    Strand,
    Value,
)
from fpl.errors import FplError, Span

type Builtin = Callable[..., tuple[Value, ...]]


@dataclass(frozen=True)
class State:
    """The stack, top last; the code still to run; the definitions by name."""

    stack: tuple[Value, ...]
    code: tuple[Node, ...]
    words: Mapping[str, tuple[Node, ...]]


def evaluate(statements: tuple[Statement, ...]) -> tuple[tuple[Value, ...], ...]:
    """The stack each run line leaves, every line on a fresh stack. A later definition of a
    name shadows an earlier one, for every line."""
    words = {s.name: s.code for s in statements if isinstance(s, Define)}
    return tuple(final(State((), s.code, words)) for s in statements if isinstance(s, Run))


def final(state: State) -> tuple[Value, ...]:
    """The stack once no code is left."""
    while state.code:
        state = step(state)
    return state.stack


def running(state: State) -> bool:
    """Some code is left to run."""
    return bool(state.code)


@icontract.require(running)
def step(state: State) -> State:
    """Run the first node: push its value, put a defined word's code in its place, or apply a
    builtin to the values it takes."""
    node, rest = state.code[0], state.code[1:]
    match node:
        case Push():
            return State((*state.stack, node.value), rest, state.words)
        case Call() if node.name in state.words:
            return State(state.stack, state.words[node.name] + rest, state.words)
        case Call():
            return State(builtin(node, state.stack), rest, state.words)
        case _:
            assert_never(node)


def builtin(call: Call, stack: tuple[Value, ...]) -> tuple[Value, ...]:
    """The stack with a builtin's results in place of its arguments. Fewer values than it takes
    is refused at the word: an effect line promised more than its body left."""
    cut = len(stack) - len(EFFECTS[call.name].ins)
    if cut < 0:
        raise FplError(call.span, "stack underflow")
    return (*stack[:cut], *BUILTINS[call.name](call.span, *stack[cut:]))


def operands(value: Value, span: Span) -> tuple[Number, ...]:
    """A number as one operand, a strand of numbers as its items; anything else is refused."""
    items = value.items if isinstance(value, Strand) else (value,)
    numbers = tuple(item for item in items if isinstance(item, int | Decimal))
    if len(numbers) < len(items):
        raise FplError(span, "arithmetic on a non-number")
    return numbers


def arithmetic(op: Callable[[Number, Number], Number]) -> Builtin:
    """A pervasive operator: a number meets a number, or each item of a strand; two strands
    meet item by item and must be as long."""

    def apply(span: Span, a: Value, b: Value) -> tuple[Value, ...]:
        xs, ys = operands(a, span), operands(b, span)
        if len(xs) != len(ys) and 1 not in (len(xs), len(ys)):
            raise FplError(span, "strands of unequal length")
        width = max(len(xs), len(ys))
        zs = tuple(
            op(x, y) for x, y in zip(xs * (width // len(xs)), ys * (width // len(ys)), strict=True)
        )
        return (Strand(zs) if isinstance(a, Strand) or isinstance(b, Strand) else zs[0],)

    return apply


def swap(_span: Span, a: Value, b: Value) -> tuple[Value, ...]:
    """x y -- y x"""
    return b, a


def dup(_span: Span, a: Value) -> tuple[Value, ...]:
    """x -- x x"""
    return a, a


def drop(_span: Span, _a: Value) -> tuple[Value, ...]:
    """x --"""
    return ()


def enclose(_span: Span, a: Value) -> tuple[Value, ...]:
    """x -- [x]"""
    return (Quotation((Push(a),)),)


def join(span: Span, a: Value, b: Value) -> tuple[Value, ...]:
    """Two quotations as one, or two lists as one."""
    match a, b:
        case Quotation(), Quotation():
            return (Quotation(a.code + b.code),)
        case Listed(), Listed():
            return (Listed(a.items + b.items),)
        case _:
            raise FplError(span, ", joins two quotations or two lists")


BUILTINS: dict[str, Builtin] = {
    "+": arithmetic(lambda x, y: x + y),
    "-": arithmetic(lambda x, y: x - y),
    "times": arithmetic(lambda x, y: x * y),
    "swap": swap,
    "dup": dup,
    "drop": drop,
    "enclose": enclose,
    ",": join,
}
