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
    Equal,
    Guarded,
    Inverse,
    Keyed,
    Listed,
    Match,
    Node,
    Number,
    Pattern,
    Push,
    Quotation,
    Row,
    Run,
    Statement,
    Strand,
    Value,
    Var,
    Wild,
)
from fpl.errors import FplError, Span

type Builtin = Callable[..., tuple[Value, ...]]
type Words = Mapping[str, tuple[Node, ...]]
type Control = Callable[..., tuple[Node, ...]]
type Bound = dict[str, Value]
type Stack = tuple[Value, ...]


@dataclass(frozen=True)
class State:
    """The stack, top last; the code still to run; the definitions by name."""

    stack: tuple[Value, ...]
    code: tuple[Node, ...]
    words: Words


def evaluate(statements: tuple[Statement, ...]) -> tuple[tuple[Value, ...], ...]:
    """The stack each run line leaves, every line on a fresh stack. A later definition of a
    name shadows an earlier one, for every line; name/history pushes the ones it shadows,
    oldest first, each as a quotation, name/doc the docstring of the one in force and
    name/effect its effect line as a list of strings, +fail last when it may fail."""
    logged: dict[str, list[Define]] = {}
    for s in statements:
        if isinstance(s, Define):
            logged.setdefault(s.name, []).append(s)
    words = {name: log[-1].code for name, log in logged.items()}
    for name, log in logged.items():
        words[f"{name}/history"] = (Push(Listed(tuple(Quotation(d.code) for d in log[:-1]))),)
        words[f"{name}/doc"] = (Push(log[-1].doc),)
        words[f"{name}/effect"] = (Push(effect_line(log[-1])),)
    return tuple(final(State((), s.code, words)) for s in statements if isinstance(s, Run))


def effect_line(define: Define) -> Listed:
    """ins -- outs, then +fail if the word may fail."""
    effect = define.effect
    fails = ("+fail",) if effect.fails else ()
    return Listed((*effect.ins, "--", *effect.outs, *fails))


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
    place, and a match the body of the row it chose."""
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
        case Match():
            return matching(node, state, rest)
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
            return rekeyed(node, name, value)
        case Match():
            return rematched(node, name, value)
        case _:
            assert_never(node)


def rekeyed(node: Keyed, name: str, value: Value) -> Keyed:
    """A dict's values with name standing for value."""
    return Keyed(tuple((key, replaced(n, name, value)) for key, n in node.entries), node.span)


def rematched(node: Match, name: str, value: Value) -> Match:
    """A match's rows with name standing for value."""
    return Match(tuple(rebound(row, name, value) for row in node.rows), node.span)


def rebound(row: Row, name: str, value: Value) -> Row:
    """A row with name standing for value, up to the pattern that binds name anew."""
    patterns: list[Pattern] = []
    shadowed = False
    for pattern in row.patterns:
        patterns.append(pattern if shadowed else pinned(pattern, name, value))
        shadowed = shadowed or name in names(pattern)
    body = row.body if shadowed else substitute(row.body, name, value)
    return Row(tuple(patterns), body)


def pinned(pattern: Pattern, name: str, value: Value) -> Pattern:
    """A pattern with each $name the value it pins."""
    match pattern:
        case Equal():
            return Equal(replaced(pattern.node, name, value))
        case Inverse():
            args = tuple(pinned(p, name, value) for p in pattern.args)
            return Inverse(pattern.name, args, pattern.span)
        case Guarded():
            return Guarded(pinned(pattern.pattern, name, value), pattern.test, pattern.span)
        case Wild() | Var():
            return pattern
        case _:
            assert_never(pattern)


def names(pattern: Pattern) -> frozenset[str]:
    """The names a pattern binds."""
    match pattern:
        case Var():
            return frozenset((pattern.name,))
        case Inverse():
            return frozenset[str]().union(*map(names, pattern.args))
        case Guarded():
            return names(pattern.pattern)
        case Wild() | Equal():
            return frozenset()
        case _:
            assert_never(pattern)


def matching(node: Match, state: State, rest: tuple[Node, ...]) -> State:
    """The values the match takes replaced by the body of the first row matching them, each
    name a pattern bound standing for its value; no row matching raises +fail at the match."""
    cut = len(state.stack) - len(node.rows[0].patterns)
    if cut < 0:
        raise FplError(node.span, "stack underflow")
    for row in node.rows:
        bound = matches(row.patterns, state.stack[cut:], state.words)
        if bound is not None:
            code = row.body
            for name, value in bound.items():
                code = substitute(code, name, value)
            return State(state.stack[:cut], code + rest, state.words)
    raise FplError(node.span, "no row matches")


def matches(patterns: tuple[Pattern, ...], values: Stack, words: Words) -> Bound | None:
    """Each pattern against its value, left to right, a name bound by one pinned in those
    after it; None if one fails."""
    bound: Bound = {}
    for pattern, value in zip(patterns, values, strict=True):
        for name, earlier in bound.items():
            pattern = pinned(pattern, name, earlier)  # noqa: PLW2901 -- pinned in turn
        got = matched(pattern, value, words)
        if got is None:
            return None
        bound |= got
    return bound


def matched(pattern: Pattern, value: Value, words: Words) -> Bound | None:
    """What one pattern binds on a value, or None: a guard is its word leaving 1 on the
    value (hole guard-test)."""
    match pattern:
        case Wild():
            return {}
        case Var():
            return {pattern.name: value}
        case Equal():
            return {} if pattern.node == Push(value) else None
        case Guarded():
            bound = matched(pattern.pattern, value, words)
            test = final(State((value,), (Call(pattern.test, pattern.span),), words))
            return bound if test == (1,) else None
        case Inverse():
            return unbuilt(pattern, value, words)
        case _:
            assert_never(pattern)


def unbuilt(pattern: Inverse, value: Value, words: Words) -> Bound | None:
    """What the arguments bind on the values the constructor, run backwards, gives."""
    given = undone(pattern.name, (value,), words, pattern.span)
    if given is None or len(given) != len(pattern.args):
        return None
    return matches(pattern.args, given, words)


def undone(
    name: str, stack: Stack, words: Words, span: Span, trail: frozenset[str] = frozenset()
) -> Stack | None:
    """The stack with the word run backwards on its top, or None where the top is not a value
    it builds. A defined word runs its body backwards, a primitive its inverse; any other
    word, or a word inside its own body, is refused where the pattern names it."""
    if name in words and name not in trail:
        state: Stack | None = stack
        for node in reversed(words[name]):
            if state is None:
                return None
            state = unrun(node, state, words, span, trail | {name})
        return state
    if name in words or name not in INVERSES:
        raise FplError(span, f"{name} is not invertible")
    return INVERSES[name](stack)


def unrun(
    node: Node, stack: Stack, words: Words, span: Span, trail: frozenset[str]
) -> Stack | None:
    """One node of a constructor's body run backwards: a push takes its value back off."""
    match node:
        case Push():
            return unpush(node.value, stack)
        case Call():
            return undone(node.name, stack, words, span, trail)
        case _:
            raise FplError(span, "a constructor is words and literals: not invertible")


def unpush(value: Value, stack: Stack) -> Stack | None:
    """The stack below its top, when the top is the value."""
    match stack:
        case (*below, top) if top == value:
            return tuple(below)
        case _:
            return None


def unswap(stack: Stack) -> Stack | None:
    """swap is its own inverse."""
    match stack:
        case (*below, x, y):
            return (*below, y, x)
        case _:
            return None


def unpair(stack: Stack) -> Stack | None:
    """A pair's two items."""
    match stack:
        case (*below, Listed(items=(a, b))):
            return (*below, a, b)
        case _:
            return None


def uncons(stack: Stack) -> Stack | None:
    """A non-empty list's first item and the rest."""
    match stack:
        case (*below, Listed(items=(x, *xs))):
            return (*below, x, Listed(tuple(xs)))
        case _:
            return None


INVERSES: dict[str, Callable[[Stack], Stack | None]] = {
    "swap": unswap,
    "pair": unpair,
    "cons": uncons,
}


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


def pair(_span: Span, a: Value, b: Value) -> tuple[Value, ...]:
    """a b -- p : a two-item list (hole pair-shape)."""
    return (Listed((a, b)),)


def cons(span: Span, x: Value, xs: Value) -> tuple[Value, ...]:
    """x xs -- ys : x before the items of a list."""
    if not isinstance(xs, Listed):
        raise FplError(span, "cons takes a list")
    return (Listed((x, *xs.items)),)


def unfilled(span: Span) -> tuple[Value, ...]:
    """-- : a goal left in the code, refused where it runs (hole goal-placeholder)."""
    raise FplError(span, "unfilled goal")


def nothing(_span: Span) -> tuple[Value, ...]:
    """-- : a _ the elaborator inferred as nothing (hole infer-hole)."""
    return ()


BUILTINS: dict[str, Builtin] = {
    "+": partial(arithmetic, lambda x, y: x + y),
    "-": partial(arithmetic, lambda x, y: x - y),
    "times": partial(arithmetic, lambda x, y: x * y),
    "swap": swap,
    "dup": dup,
    "?": unfilled,
    "_": nothing,
    "drop": drop,
    "enclose": enclose,
    ",": join,
    "pair": pair,
    "cons": cons,
}


def quoted(value: Value, span: Span) -> Quotation:
    """A value that must be a quotation."""
    if not isinstance(value, Quotation):
        raise FplError(span, "a quotation is expected")
    return value


def force(span: Span, _words: Words, q: Value) -> tuple[Node, ...]:
    """q -- : q run in place; q fills a thunk slot, as every control word's quotation does."""
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
    values = items(xs, span)
    results = list(values[:1])
    for x in values[1:]:
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
