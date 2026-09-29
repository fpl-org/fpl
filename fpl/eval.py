"""The core as a step machine: a state is the stack and the code still to run, and `step` runs
one node of it. Over the core AST only."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from functools import partial
from typing import assert_never

import icontract

from fpl.ast_core import (
    EFFECTS,
    Bind,
    Call,
    Define,
    Dict,
    Keyed,
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
type Words = Mapping[str, tuple[Node, ...]]
type Control = Callable[..., tuple[Node, ...]]


@dataclass(frozen=True)
class State:
    """The stack, top last; the code still to run; the definitions by name."""

    stack: tuple[Value, ...]
    code: tuple[Node, ...]
    words: Words


def evaluate(statements: tuple[Statement, ...]) -> tuple[tuple[Value, ...], ...]:
    """The stack each run line leaves, every line on a fresh stack. A later definition of a
    name shadows an earlier one, for every line; name/history pushes the ones it shadows,
    oldest first, each as a quotation."""
    logged: dict[str, list[tuple[Node, ...]]] = {}
    for s in statements:
        if isinstance(s, Define):
            logged.setdefault(s.name, []).append(s.code)
    words = {name: log[-1] for name, log in logged.items()}
    for name, log in logged.items():
        words[f"{name}/history"] = (Push(Listed(tuple(map(Quotation, log[:-1])))),)
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
    """Run the first node: push its value, put a defined word's code in its place, apply a
    builtin to the values it takes, put a binder's scope in its place with the top for its
    name, or push the dict its values build. A control word puts the code it runs in its
    place."""
    node, rest = state.code[0], state.code[1:]
    match node:
        case Push():
            return State((*state.stack, node.value), rest, state.words)
        case Bind():
            if not state.stack:
                raise FplError(node.span, "stack underflow")
            scope = substitute(node.body, node.name, state.stack[-1])
            return State(state.stack[:-1], scope + rest, state.words)
        case Keyed():
            return State((*state.stack, gathered(node, state.words)), rest, state.words)
        case Call() if node.name in state.words:
            return State(state.stack, state.words[node.name] + rest, state.words)
        case Call():
            return builtin(node, state, rest)
        case _:
            assert_never(node)


def substitute(code: tuple[Node, ...], name: str, value: Value) -> tuple[Node, ...]:
    """The code with every call of name, in quotations too, a push of value; a binder of the
    same name shadows it for its scope."""
    return tuple(replaced(node, name, value) for node in code)


def replaced(node: Node, name: str, value: Value) -> Node:
    """One node with name standing for value."""
    match node:
        case Call():
            return Push(value) if node.name == name else node
        case Push():
            return Push(held(node.value, name, value))
        case Bind():
            body = node.body if node.name == name else substitute(node.body, name, value)
            return Bind(node.name, body, node.span)
        case Keyed():
            entries = tuple((key, replaced(n, name, value)) for key, n in node.entries)
            return Keyed(entries, node.span)
        case _:
            assert_never(node)


def held(inner: Value, name: str, value: Value) -> Value:
    """A pushed value with name standing for value in the code it holds."""
    match inner:
        case Quotation():
            return Quotation(substitute(inner.code, name, value))
        case Listed():
            return Listed(tuple(held(item, name, value) for item in inner.items))
        case _:
            return inner


def gathered(node: Keyed, words: Words) -> Dict:
    """Each value run on a fresh stack, where it must leave one value."""
    entries: list[tuple[str, Value]] = []
    for key, code in node.entries:
        stack = final(State((), (code,), words))
        if len(stack) != 1:
            raise FplError(node.span, "a dict value is one value")
        entries.append((key, stack[0]))
    return Dict(tuple(entries))


def builtin(call: Call, state: State, rest: tuple[Node, ...]) -> State:
    """The state with a builtin's results in place of its arguments, or with a control word's
    code before the rest. Fewer values than it takes is refused at the word: an effect line
    promised more than its body left."""
    cut = len(state.stack) - len(EFFECTS[call.name].ins)
    if cut < 0:
        raise FplError(call.span, "stack underflow")
    below, taken = state.stack[:cut], state.stack[cut:]
    if call.name in CONTROLS:
        code = CONTROLS[call.name](call.span, state.words, *taken)
        return State(below, code + rest, state.words)
    return State((*below, *BUILTINS[call.name](call.span, *taken)), rest, state.words)


def operands(value: Value, span: Span) -> tuple[Number, ...]:
    """A number as one operand, a strand of numbers as its items; anything else is refused."""
    items = value.items if isinstance(value, Strand) else (value,)
    numbers = tuple(item for item in items if isinstance(item, int | Decimal))
    if len(numbers) < len(items):
        raise FplError(span, "arithmetic on a non-number")
    return numbers


def arithmetic(
    op: Callable[[Number, Number], Number], span: Span, a: Value, b: Value
) -> tuple[Value, ...]:
    """A pervasive operator: a number meets a number, or each item of a strand; two strands
    meet item by item and must be as long."""
    xs, ys = operands(a, span), operands(b, span)
    if len(xs) != len(ys) and 1 not in (len(xs), len(ys)):
        raise FplError(span, "strands of unequal length")
    zs = tuple(op(xs[i % len(xs)], ys[i % len(ys)]) for i in range(max(len(xs), len(ys))))
    return (Strand(zs) if isinstance(a, Strand) or isinstance(b, Strand) else zs[0],)


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
    "+": partial(arithmetic, lambda x, y: x + y),
    "-": partial(arithmetic, lambda x, y: x - y),
    "times": partial(arithmetic, lambda x, y: x * y),
    "swap": swap,
    "dup": dup,
    "drop": drop,
    "enclose": enclose,
    ",": join,
}


def quoted(value: Value, span: Span) -> Quotation:
    """A value that must be a quotation."""
    if not isinstance(value, Quotation):
        raise FplError(span, "a quotation is expected")
    return value


def force(span: Span, _words: Words, q: Value) -> tuple[Node, ...]:
    """q -- : q run in place; a quotation forced is a thunk (hole thunk-or-code)."""
    return quoted(q, span).code


def choose(span: Span, _words: Words, c: Value, t: Value, e: Value) -> tuple[Node, ...]:
    """c t e -- : t run in place on 1, e on 0; any other condition is refused (hole
    truth-values)."""
    branches = quoted(e, span), quoted(t, span)
    if not isinstance(c, int) or c not in (0, 1):
        raise FplError(span, "if takes 0 or 1")
    return branches[c].code


def commute(span: Span, _words: Words, x: Value, y: Value, q: Value) -> tuple[Node, ...]:
    """x y q -- : q run in place on y x."""
    return (Push(y), Push(x), *quoted(q, span).code)


def repeat(span: Span, _words: Words, q: Value, n: Value) -> tuple[Node, ...]:
    """q n -- : q run in place n times; n a count. Each round puts back one q and the rest of
    the count, so the code grows by one q, not n."""
    code = quoted(q, span).code
    if not isinstance(n, int) or n < 0:
        raise FplError(span, "repeat takes a count")
    if n == 0:
        return ()
    return (*code, Push(q), Push(n - 1), Call("repeat", span))


def items(xs: Value, span: Span) -> tuple[Value, ...]:
    """The items of a strand or a list; anything else is refused."""
    if not isinstance(xs, Strand | Listed):
        raise FplError(span, "a strand or a list is expected")
    return xs.items


def single(state: State, span: Span) -> Value:
    """The one value a step leaves on its fresh stack (hole step-stack)."""
    stack = final(state)
    if len(stack) != 1:
        raise FplError(span, "each step leaves one value")
    return stack[0]


def rebuilt(xs: Value, values: list[Value]) -> Push:
    """The results pushed as a strand when xs was one and every result is a number or a
    string, else as a list (hole sequence-shape)."""
    atoms = tuple(v for v in values if isinstance(v, int | Decimal | str))
    if isinstance(xs, Strand) and len(atoms) == len(values):
        return Push(Strand(atoms))
    return Push(Listed(tuple(values)))


def running_results(span: Span, words: Words, xs: Value, q: Value) -> list[Value]:
    """The first item, then q run on the result so far and the next item, for each item."""
    code = quoted(q, span).code
    results = list(items(xs, span)[:1])
    for x in items(xs, span)[1:]:
        results.append(single(State((results[-1], x), code, words), span))
    return results


def each(span: Span, words: Words, xs: Value, q: Value) -> tuple[Node, ...]:
    """xs q -- ys : q run on each item alone."""
    code = quoted(q, span).code
    return (rebuilt(xs, [single(State((x,), code, words), span) for x in items(xs, span)]),)


def scan(span: Span, words: Words, xs: Value, q: Value) -> tuple[Node, ...]:
    """xs q -- ys : every result a fold passes through."""
    return (rebuilt(xs, running_results(span, words, xs, q)),)


def fold(span: Span, words: Words, xs: Value, q: Value) -> tuple[Node, ...]:
    """xs q -- x : the last result of the scan; no item to start from is refused."""
    results = running_results(span, words, xs, q)
    if not results:
        raise FplError(span, "fold over nothing")
    return (Push(results[-1]),)


CONTROLS: dict[str, Control] = {
    "!": force,
    "if": choose,
    "swap-args": commute,
    "repeat": repeat,
    "each": each,
    "scan": scan,
    "fold": fold,
}
