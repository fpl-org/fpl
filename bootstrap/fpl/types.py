"""Elaboration over the core AST: each word's effect inferred from its body and checked against
its effect line, before any line runs.

A sort is what elaboration knows of a value: a number, a text, a symbol, or a value of no sort
it tracks (a list, a quotation, a dict, what a control word leaves: trusted, hole typed-fragment).
While a body is inferred, the values it takes are inputs whose sorts are not known yet; arithmetic
on one makes it a number. An arrow is a word's inferred effect: the sorts it takes and leaves.
A ? is a goal: reported with the arrow that would fill it, elaboration going on past it; a _ is
inferred as nothing, or refused (holes goal-placeholder, infer-hole).
"""

from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import Enum, IntEnum
from typing import assert_never

from fpl.ast_core import (
    EFFECTS,
    Bind,
    Call,
    Define,
    Equal,
    Guarded,
    Inverse,
    Keyed,
    Match,
    Node,
    Pattern,
    Push,
    Refuse,
    Row,
    Run,
    Statement,
    Strand,
    Symbol,
    Value,
    Var,
    Wild,
)
from fpl.errors import FplError, Span
from fpl.eval import CONTROLS


@dataclass(frozen=True)
class Input:
    """The index-th value a word takes, its sort not known yet."""

    index: int


class Verdict(IntEnum):
    """Whether values of known sorts fit a pattern: surely not, perhaps, surely; a conjunction
    is the least of its parts."""

    NO = 0
    MAYBE = 1
    YES = 2


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
class Dispatch(Arrow):
    """A dispatcher's arrow, and its rows in the order it tries them (design 09 §3.6)."""

    rows: tuple[Row, ...]


@dataclass(frozen=True)
class Goal:
    """A ? met: where it is and the arrow that would fill it."""

    span: Span
    arrow: Arrow


@dataclass(frozen=True)
class Typing:
    """What elaboration knows at a point in the code: the sorts on the stack, top last; the sort
    each bound name stands for; the sorts the body's inputs have been found to be; the goals
    met so far; whether the code gets here, which a refusal never passes."""

    stack: tuple[Sort, ...]
    env: Mapping[str, Sort]
    known: Mapping[int, Sort]
    goals: tuple[Goal, ...] = ()
    reached: bool = True


class UntypedError(Exception):
    """Code outside what elaboration infers (a control word, whose effect is the code it runs; a
    match whose rows disagree): its word's effect line is trusted."""


class UnderflowError(FplError):
    """Fewer values than a word, a binder or a match takes."""

    def __init__(self, span: Span) -> None:
        """An underflow at the word, binder or match the span points to; the message is always
        the same."""
        super().__init__(span, "stack underflow")


HOLES = ("?", "_")
NUMBERS = Arrow((Kind.NUMBER, Kind.NUMBER), (Kind.NUMBER,))
ARROWS: dict[str, Arrow] = {
    **{
        name: Arrow(tuple(map(Input, range(len(e.ins)))), (Kind.VALUE,) * len(e.outs))
        for name, e in EFFECTS.items()
        if name not in CONTROLS and name not in HOLES
    },
    "+": NUMBERS,
    "-": NUMBERS,
    "times": NUMBERS,
    "swap": Arrow((Input(0), Input(1)), (Input(1), Input(0))),
    "dup": Arrow((Input(0),), (Input(0), Input(0))),
    "drop": Arrow((Input(0),), ()),
}
QUERIES = ("history", "doc", "effect")
TESTED = {"Int": Kind.NUMBER, "Decimal": Kind.NUMBER, "Text": Kind.TEXT, "Symbol": Kind.SYMBOL}


def elaborate(statements: tuple[Statement, ...]) -> tuple[dict[str, Arrow], tuple[Goal, ...]]:
    """Every word's arrow, builtins and queries too, and the goals met, in the order written.
    A body that leaves another count than its effect line promises is refused at its
    definition, and a sort a word cannot take, in a body or a line, at the word. A word called
    before its last definition is inferred meets that definition's effect line. A goal in code
    that is not typed is not met."""
    arrows = dict(ARROWS)
    defines = [s for s in statements if isinstance(s, Define)]
    for d in defines:
        arrows[d.word] = dispatching(d, declared(d))
        arrows.update({f"{d.word}/{query}": Arrow((), (Kind.VALUE,)) for query in QUERIES})
    last = {d.word: d for d in defines}
    goals: list[Goal] = []
    for s in statements:
        with suppress(UntypedError):
            goals.extend(checked(s, last, arrows))
    return arrows, tuple(goals)


def checked(
    statement: Statement, last: Mapping[str, Define], arrows: dict[str, Arrow]
) -> tuple[Goal, ...]:
    """The goals a statement meets; a word's last definition sets its arrow."""
    if isinstance(statement, Run):
        return after(Typing((), {}, {}), statement.code, arrows).goals
    arrow, goals = inferred(statement, arrows)
    if last[statement.word] is statement:
        arrows[statement.word] = dispatching(statement, arrow)
    return goals


def dispatching(define: Define, arrow: Arrow) -> Arrow:
    """A dispatcher's arrow with its rows; any other word's as it is."""
    match define.code:
        case (Match(rows=rows),) if len(define.clause) == 1:
            return Dispatch(arrow.ins, arrow.outs, rows)
        case _:
            return arrow


def declared(define: Define) -> Arrow:
    """The effect line as an arrow: any values in, values of no known sort out."""
    ins = tuple(map(Input, range(len(define.effect.ins))))
    return Arrow(ins, (Kind.VALUE,) * len(define.effect.outs))


def inferred(define: Define, arrows: Mapping[str, Arrow]) -> tuple[Arrow, tuple[Goal, ...]]:
    """The arrow of the body, its inputs as general as the body lets them be, and the goals it
    meets; the effect line's, and none, if the body is untyped."""
    start = Typing(tuple(map(Input, range(len(define.effect.ins)))), {}, {})
    promised = len(define.effect.outs)
    try:
        end = after(start, define.code, arrows, promised)
    except UntypedError:
        return declared(define), ()
    if len(end.stack) != promised:
        message = f"leaves {len(end.stack)} values, its effect line {promised}"
        raise FplError(define.span, f"{define.word} {message}")
    return Arrow(resolved(start.stack, end), resolved(end.stack, end)), end.goals


def resolved(sorts: tuple[Sort, ...], typing: Typing) -> tuple[Sort, ...]:
    """The sorts with each input found to be of a sort replaced by it."""
    return tuple(known(s, typing) for s in sorts)


def known(s: Sort, typing: Typing) -> Sort:
    """An input's sort once found, else the sort itself."""
    return typing.known.get(s.index, s) if isinstance(s, Input) else s


def after(
    typing: Typing, code: tuple[Node, ...], arrows: Mapping[str, Arrow], need: int | None = None
) -> Typing:
    """What is known once the code has run, `need` the count it must end at when known; a node
    that cannot run is refused at its span."""
    for index, node in enumerate(code):
        rest = code[index + 1 :]
        if isinstance(node, Call) and node.name in HOLES and node.name not in typing.env:
            typing = filled(typing, node, rest, arrows, need)
        else:
            typing = through(typing, node, arrows, None if rest else need)
    return typing


def filled(
    typing: Typing,
    node: Call,
    rest: tuple[Node, ...],
    arrows: Mapping[str, Arrow],
    need: int | None,
) -> Typing:
    """A ? takes the stack under it and leaves values of no known sort, as many as the rest
    takes, and a goal with those values' sorts; a _ is nothing, when the rest takes the stack
    as it is, else refused at it."""
    arrow = Arrow(resolved(typing.stack, typing), wanted(typing, rest, arrows, need))
    if node.name == "?":
        stack = (Kind.VALUE,) * len(arrow.outs)
        return replace(typing, stack=stack, goals=(*typing.goals, Goal(node.span, arrow)))
    if len(arrow.outs) != len(arrow.ins):
        raise FplError(node.span, f"cannot infer _ : {shown(arrow)}")
    return typing


def wanted(
    typing: Typing, rest: tuple[Node, ...], arrows: Mapping[str, Arrow], need: int | None
) -> tuple[Sort, ...]:
    """The sorts of the fewest values the rest runs on, ending at `need` values when known; a
    value the rest puts no sort on is of none."""
    count = 0
    while True:
        start = Typing(tuple(map(Input, range(count))), typing.env, {})
        with suppress(UnderflowError):
            end = after(start, rest, arrows, need)
            if need is None or len(end.stack) >= need:
                found = resolved(start.stack, end)
                return tuple(Kind.VALUE if isinstance(s, Input) else s for s in found)
        count += 1


def shown(arrow: Arrow) -> str:
    """An arrow as an effect line: an input as t and its index."""
    names = [f"t{s.index}" if isinstance(s, Input) else s.value for s in (*arrow.ins, *arrow.outs)]
    return " ".join([*names[: len(arrow.ins)], "--", *names[len(arrow.ins) :]])


def reported(goal: Goal) -> str:
    """The line a goal is reported as."""
    return f"GOAL {goal.span.line}:{goal.span.col} ? : {shown(goal.arrow)}"


def through(
    typing: Typing, node: Node, arrows: Mapping[str, Arrow], need: int | None = None
) -> Typing:
    """What is known once one node has run."""
    match node:
        case Push():
            return replace(typing, stack=(*typing.stack, sort(node.value)))
        case Keyed():
            return replace(typing, stack=(*typing.stack, Kind.VALUE))
        case Bind():
            return bound(typing, node, arrows, need)
        case Call():
            return called(typing, node, arrows)
        case Match():
            return matched(typing, node, arrows, need)
        case Refuse():
            return replace(typing, reached=False)
        case _:
            assert_never(node)


def bound(typing: Typing, node: Bind, arrows: Mapping[str, Arrow], need: int | None) -> Typing:
    """The top taken and named for the binder's scope, which runs; the name dies with it."""
    if not typing.stack:
        raise UnderflowError(node.span)
    env = {**typing.env, node.name: typing.stack[-1]}
    end = after(replace(typing, stack=typing.stack[:-1], env=env), node.body, arrows, need)
    return replace(end, env=typing.env)


def matched(typing: Typing, node: Match, arrows: Mapping[str, Arrow], need: int | None) -> Typing:
    """Each row run on the values under those the match takes, its pattern names standing for
    values of no known sort; the sorts the rows agree on, where they leave as many values,
    else untyped. Every row counts, one after a sure fit included: a sort a row finds for an
    input holds for the rows after it and the word, whichever row runs, and what a row that
    never runs leaves joins the agreement, so no pruning of rows can let the word leave a sort
    it does not promise (hole typed-fragment); pruning serves only `chosen`."""
    cut = len(typing.stack) - len(node.rows[0].patterns)
    if cut < 0:
        raise UnderflowError(node.span)
    ends: list[Typing] = []
    for row in node.rows:
        names = dict.fromkeys(bindings(row.patterns), Kind.VALUE)
        begun = replace(typing, stack=typing.stack[:cut], env={**typing.env, **names})
        ends.append(after(begun, row.body, arrows, need))
        typing = replace(typing, known=ends[-1].known, goals=ends[-1].goals)
    return replace(typing, stack=agreed(ends))


def agreed(ends: list[Typing]) -> tuple[Sort, ...]:
    """The sorts rows leave, inputs resolved by what every row found: each where they agree,
    else of no known sort; untyped where they leave different counts. A row that refuses
    leaves nothing."""
    stacks = {resolved(end.stack, ends[-1]) for end in ends if end.reached}
    if len({len(stack) for stack in stacks}) != 1:
        raise UntypedError
    columns = map(set, zip(*stacks, strict=True))
    return tuple(column.pop() if len(column) == 1 else Kind.VALUE for column in columns)


def bindings(patterns: tuple[Pattern, ...]) -> tuple[str, ...]:
    """The names patterns bind, in the order written."""
    return tuple(name for pattern in patterns for name in bound_by(pattern))


def bound_by(pattern: Pattern) -> tuple[str, ...]:
    """The names one pattern binds."""
    match pattern:
        case Var():
            return (pattern.name,)
        case Guarded():
            return bound_by(pattern.pattern)
        case Inverse():
            return bindings(pattern.args)
        case Wild() | Equal():
            return ()
        case _:
            assert_never(pattern)


def called(typing: Typing, node: Call, arrows: Mapping[str, Arrow]) -> Typing:
    """A bound name pushes the sort it stands for; a word takes and leaves its arrow's sorts."""
    if node.name in typing.env:
        return replace(typing, stack=(*typing.stack, typing.env[node.name]))
    if node.name not in arrows:
        raise UntypedError
    return applied(typing, chosen(typing, arrows[node.name], arrows), node.span)


def chosen(typing: Typing, arrow: Arrow, arrows: Mapping[str, Arrow]) -> Arrow:
    """The arrow a call applies: a dispatcher's resolved to its clause's when exactly one row
    survives, it is a clause's, no value is an input and, where the row only may fit, the
    clause takes the values' sorts, since the run would miss where it refuses; else the arrow
    as it is."""
    cut = len(typing.stack) - len(arrow.ins)
    if not isinstance(arrow, Dispatch) or cut < 0:
        return arrow
    sorts = resolved(typing.stack[cut:], typing)
    if any(isinstance(s, Input) for s in sorts):
        return arrow
    match surviving(arrow.rows, sorts, arrows):
        case (Row(body=(*_, Call(name=clause))) as row,):
            found = arrows[clause]
            if verdict(row, sorts, arrows) is Verdict.YES or taken(found, sorts):
                return found
            return arrow
        case _:
            return arrow


def surviving(
    rows: tuple[Row, ...], sorts: tuple[Sort, ...], arrows: Mapping[str, Arrow]
) -> tuple[Row, ...]:
    """The rows values of the sorts may take, in order: those that surely miss dropped, none
    after the first that surely fits."""
    kept: list[Row] = []
    for row in rows:
        fit = verdict(row, sorts, arrows)
        if fit is not Verdict.NO:
            kept.append(row)
        if fit is Verdict.YES:
            break
    return tuple(kept)


def verdict(row: Row, sorts: tuple[Sort, ...], arrows: Mapping[str, Arrow]) -> Verdict:
    """How surely values of the sorts fit the row's patterns."""
    fits = (fitted(have, p, arrows) for have, p in zip(sorts, row.patterns, strict=True))
    return min(fits, default=Verdict.YES)


def fitted(have: Sort, pattern: Pattern, arrows: Mapping[str, Arrow]) -> Verdict:
    """How surely a value of the sort fits the pattern: a name or _ surely does; a guarded
    pattern, an ascription `x: w` included, at most may, and surely not where its pattern or
    its test surely misses; a literal or a constructor may."""
    match pattern:
        case Var() | Wild():
            return Verdict.YES
        case Guarded():
            return min(fitted(have, pattern.pattern, arrows), tested(have, pattern.test, arrows))
        case Equal() | Inverse():
            return Verdict.MAYBE
        case _:
            assert_never(pattern)


def tested(have: Sort, test: str, arrows: Mapping[str, Arrow]) -> Verdict:
    """How surely a test leaves 1 on a value of the sort, never surely: the word runs on the
    value only at run time, so a guarded row is never a sure fit and pruning never stops at
    it. A builtin type word surely does not on a known sort other than its own; on its own
    sort, an input or a value of no known sort it may, as any other test may, a type word the
    program redefines included."""
    want = TESTED.get(test)
    if want is None or arrows.get(test) is not ARROWS[test]:
        return Verdict.MAYBE
    if isinstance(have, Input) or have in (Kind.VALUE, want):
        return Verdict.MAYBE
    return Verdict.NO


def taken(arrow: Arrow, sorts: tuple[Sort, ...]) -> bool:
    """Whether the arrow takes values of the sorts, as `met` finds."""
    pairs = zip(arrow.ins, sorts, strict=True)
    return all(isinstance(need, Input) or have in (need, Kind.VALUE) for need, have in pairs)


def applied(typing: Typing, arrow: Arrow, span: Span) -> Typing:
    """The arrow's inputs met by the values under the top, its outputs in their place."""
    cut = len(typing.stack) - len(arrow.ins)
    if cut < 0:
        raise UnderflowError(span)
    local: dict[int, Sort] = {}
    found = dict(typing.known)
    for need, have in zip(arrow.ins, typing.stack[cut:], strict=True):
        met(need, known(have, typing), local, found, span)
    outs = tuple(local[s.index] if isinstance(s, Input) else s for s in arrow.outs)
    return replace(typing, stack=(*typing.stack[:cut], *outs), known=found)


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
