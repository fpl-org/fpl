"""Pass 2, polarise, on straight-line code: Core_A to cbpv⁻ through a static stack (design 6.3).

Promised: the walker's data stack becomes IR names. Each code tuple is walked with a static
stack of entries, an IR value with its type, and an environment from binder names to entries
(outermost binder first); the computation is built in continuation style, one `to` or
`pm … as (x, y)` per call, closed by `return` of the entries left, as a right-nested pair.

- A pushed literal that mentions no binder in scope is a `Const` of its sort's type; one that
  does is the program's own `held` constant applied to those binders' entries.
- A first-order builtin is `prim p` at the entries' types, its results typed by its 07 arrow;
  a defined word is `force f`, its results typed by what its body leaves. The results come back
  as one value and are split into names.
- `f/doc` and `f/effect` are `Const`s; a binder names the top for its scope; a dict is the
  program's own `keyed` constant over its entries, each lowered on a fresh static stack.
- A word is `thunk (λtop. … λdeepest. body)`, every binder of grade ω; a run line is its code
  over an empty static stack, returning what is left.

- `_` (a hole 07 inferred as nothing) lowers to nothing; `?` is `prim ?` of no arguments, which
  panics "unfilled goal" at its span through the walker's own function.
- A literal quotation is `Thunk(M, origin)`: its body over a static stack that grows a λ-bound
  `Dyn` input each time it pops below what it pushed, the first grown the top at entry. `!` and
  `swap-args` run a thunk entry in place on the top entries it takes; on an operand statically
  not a quotation they are the program's own `control` constant, which panics as the walker does.
- `each`, `scan` and `fold` on `xs t` are the iterating constant over `xs` and a wrapper thunk:
  `λx.` (`λx. λacc.` for scan and fold) over a fresh static stack of those names, `x` the top,
  `t` in place, returning the one entry left, boxed.
- Box rule: a thunk entry reaching a constant's, a word's or a thunk's input is first
  passed through `prim box`, so the input receives walker data.
- A match takes as many entries as a row has patterns and tries its rows in order (design
  6.3.1), up to the first that catches every value: each row's test is its patterns' left to
  right (`_` and a name test nothing, a name binds its entry for the patterns after it and the
  body, a literal or `$x` is `prim eq`, a guard is its word on a fresh static stack of the entry,
  compared with 1 through `eq`, run even when the pattern it guards failed, as the walker runs
  it), chosen by `pm`; without a catch-all the last row falls into `fail` with the walker's
  `no row matches` at the match. Each row's body runs on a fresh static stack (the surface
  gives a row body no values below the match) and the bodies' entries are joined by one `to`.
- A thunk's effect is over-approximated from its code: `fail` for a match without a catch-all
  row, and the effect of each word it calls.

Refused, returned: `QUOTATION_UNKNOWN` for `!` or `swap-args` on walker data (a `Dyn` name),
`EFFECT_MISMATCH` for a thunk run in place outside a quotation (or in a wrapper, a row body or a
guard) on fewer entries than it takes, and for a guard leaving other than one entry;
`STEP_ARITY` for a wrapper whose fresh stack is left with other than one entry;
`BRANCHES_DISAGREE` for rows leaving different counts, or entries at types with no common fit
(two base types, or two thunk types); `INVERSE_PATTERN` for a pattern pass 1 refuses.
Refused, by precondition: `if` and `repeat`, a word calling itself or in a component of more
than one word. Those lower in later passes (holes static-stack, effect-mismatch).
"""

from collections.abc import Callable, Generator, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from itertools import count

import icontract

from fpl.ast_core import (
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
    Quotation,
    Row,
    Symbol,
    Wild,
)
from fpl.ast_core import Var as Named
from fpl.cbpv.sig import FirstOrder
from fpl.cbpv.syntax import (
    App,
    Base,
    Case,
    Comp,
    Const,
    Dyn,
    Eff,
    Effects,
    Fail,
    Force,
    Inl,
    Lam,
    One,
    Position,
    Prim,
    Program,
    Return,
    SplitPair,
    Thunk,
    To,
    U,
    Unit,
    Var,
    VType,
)
from fpl.cbpv.syntax import Value as IRValue
from fpl.errors import FplError, Span
from fpl.eval import CONTROLS, effect_line
from fpl.eval import held as substituted
from fpl.lower.select import CoreA, RefusalKind, Refused
from fpl.lower.walker import (
    SAME,
    SORTS,
    Origin,
    box,
    control,
    held,
    inputs,
    instance,
    keyed,
    paired,
    results,
    typed,
)
from fpl.types import ARROWS, Input

type Entry = tuple[IRValue, VType]
type Env = Mapping[str, Entry]
type Extra = tuple[tuple[str, FirstOrder], ...]
type Lowered = tuple[Program, Extra, tuple[Origin, ...]]
type Let = Callable[[Comp], Comp]
type Test = Comp | None

ONE: Entry = (Const(1, Base("Num")), Base("Num"))
FALSE = Inl(Unit(), One())  # `truth`'s side for 0, and `eq`'s for different values
PROBE = Symbol("probe")  # stands in for a binder while looking for its mentions
OFF = frozenset(CONTROLS) - {"!", "swap-args", "each", "scan", "fold"}


class _RefusalError(Exception):
    """A refusal from deep in the walk, returned by `polarise`."""

    def __init__(self, refused: Refused) -> None:
        super().__init__(refused.detail)
        self.refused = refused


def _flat(code: tuple[Node, ...]) -> Iterator[Node]:
    """Every node of `code`, through binder scopes, dict entries and pushed quotations."""
    for node in code:
        yield node
        if isinstance(node, Push) and isinstance(node.value, Quotation):
            yield from _flat(node.value.code)
        elif isinstance(node, Bind):
            yield from _flat(node.body)
        elif isinstance(node, Keyed):
            yield from _flat(tuple(n for _, n in node.entries))
        elif isinstance(node, Match):
            yield from _rows(node)


def _rows(node: Match) -> Iterator[Node]:
    """Every node of a match's patterns' tests and rows' bodies."""
    for row in node.rows:
        yield from _flat((*_tested(row.patterns), *row.body))


def _tested(patterns: Sequence[Pattern]) -> Iterator[Node]:
    """The code a row's patterns run: a literal's or `$x`'s push, a guard's word."""
    for pattern in patterns:
        if isinstance(pattern, Equal):
            yield pattern.node
        elif isinstance(pattern, Guarded):
            yield from _tested((pattern.pattern,))
            yield Call(pattern.test, pattern.span)


def _catches(row: Row) -> bool:
    """Every pattern of the row is `_` or a name, as the walker's `catches` reads it."""
    return all(isinstance(pattern, Wild | Named) for pattern in row.patterns)


def _off(node: Node, own: str) -> bool:
    return isinstance(node, Call) and node.name in OFF | {own}


def lowerable(core: CoreA) -> bool:
    """No `if` or `repeat`, no word calling itself, one word per component."""
    owned = ((s.name if isinstance(s, Define) else "", s.code) for s in core.statements)
    plain = not any(_off(node, own) for own, code in owned for node in _flat(code))
    return plain and all(len(c) == 1 for c in core.components)


def _closed(lets: Sequence[Let], comp: Comp) -> Comp:
    """`comp` under the pending bindings, the first outermost."""
    for let in reversed(lets):
        comp = let(comp)
    return comp


def _applied(head: Comp, values: Sequence[IRValue]) -> Comp:
    """`head` applied to `values`, pushed the deepest first."""
    for value in reversed(values):
        head = App(value, head)
    return head


@dataclass(frozen=True)
class _Word:
    """A word lowered so far: the values it takes, the types of those it leaves, its effect."""

    ins: int
    outs: tuple[VType, ...]
    eff: Effects


@dataclass(frozen=True)
class _Arm:
    """A match row lowered: its test (None for a row catching every value), and its body's
    pending bindings and the entries it leaves."""

    test: Test
    lets: tuple[Let, ...]
    stack: tuple[Entry, ...]


@dataclass
class _Lowering:
    """The words lowered so far (inputs, output types), the queries they answer, the program's
    own constants, the literal quotations' origins, and the static stack, pending bindings and
    grown inputs (outside a quotation none may grow) of the code being lowered."""

    words: dict[str, _Word] = field(default_factory=dict[str, _Word])
    queries: dict[str, Const] = field(default_factory=dict[str, Const])
    extra: list[tuple[str, FirstOrder]] = field(default_factory=list[tuple[str, FirstOrder]])
    stack: list[Entry] = field(default_factory=list[Entry])
    lets: list[Let] = field(default_factory=list[Let])
    fresh: Iterator[int] = field(default_factory=count)
    origins: list[Origin] = field(default_factory=list[Origin])
    grown: list[str] | None = None

    def name(self) -> str:
        """An IR name no walker word can spell: it holds a space."""
        return f" v{next(self.fresh)}"

    def code(self, code: tuple[Node, ...], env: Env) -> None:
        for node in code:
            _NODES[type(node)](self, node, env)

    @contextmanager
    def aside(self, stack: list[Entry], grown: list[str] | None = None) -> Generator[None]:
        """Lower on `stack` with no pending bindings, then go back to the code being lowered."""
        saved = self.stack, self.lets, self.grown
        self.stack, self.lets, self.grown = stack, [], grown
        try:
            yield
        finally:
            self.stack, self.lets, self.grown = saved

    def effects(self, code: tuple[Node, ...]) -> Effects:
        """What running `code` may do besides return: `fail` for a match without a catch-all
        row, and the effect of every word it calls."""
        eff: set[Eff] = set()
        for node in _flat(code):
            if isinstance(node, Match) and not any(map(_catches, node.rows)):
                eff.add("fail")
            elif isinstance(node, Call) and node.name in self.words:
                eff |= self.words[node.name].eff
        return frozenset(eff)

    def body(self, code: tuple[Node, ...]) -> tuple[Comp, tuple[VType, ...]]:
        """`code` over the static stack, returning the entries it leaves, and their types."""
        self.lets = []
        self.code(code, {})
        return self.returned()

    def returned(self) -> tuple[Comp, tuple[VType, ...]]:
        comp = _closed(self.lets, Return(paired([v for v, _ in self.stack])))
        return comp, tuple(t for _, t in self.stack)

    def word(self, define: Define) -> Thunk:
        """`thunk (λtop. … λdeepest. body)`; its inputs are walker data (`Dyn`)."""
        names = [self.name() for _ in define.effect.ins]
        self.stack = [(Var(x), Dyn()) for x in reversed(names)]
        comp, outs = self.body(define.code)
        for x in reversed(names):
            comp = Lam(x, Dyn(), "ω", comp)
        self.words[define.name] = _Word(len(names), outs, self.effects(define.code))
        self.queries[f"{define.name}/doc"] = Const(define.doc, typed(define.doc))
        self.queries[f"{define.name}/effect"] = Const(effect_line(define), Dyn())
        return Thunk(comp)

    def quotation(self, value: Quotation, env: Env) -> Entry:
        """`Thunk(λin₁. … λinₙ. body, origin)`, its inputs grown on demand, `in₁` the top."""
        grown: list[str] = []
        with self.aside([], grown):
            self.code(value.code, env)
            comp, outs = self.returned()
        for x in reversed(grown):
            comp = Lam(x, Dyn(), "ω", comp)
        names = tuple((x, v) for x, (v, _) in env.items())
        self.origins.append(Origin(value.code, names, len(grown), len(outs)))
        thunk = Thunk(comp, len(self.origins) - 1)
        return thunk, U(instance([Dyn()] * len(grown), outs), self.effects(value.code))

    def taken(self, n: int, at: Span) -> list[Entry]:
        """The top `n` entries, the deepest first, popped; inside a quotation the missing ones
        are grown as inputs, elsewhere they are refused (the walker would underflow at `at`)."""
        short = n - len(self.stack)
        if short > 0:
            if self.grown is None:
                wanted = f"{n} values taken, {len(self.stack)} on the stack"
                raise _RefusalError(Refused(RefusalKind.EFFECT_MISMATCH, at, wanted))
            names = [self.name() for _ in range(short)]
            self.grown.extend(names)
            self.stack[:0] = [(Var(x), Dyn()) for x in reversed(names)]
        cut = len(self.stack) - n
        args = self.stack[cut:]
        del self.stack[cut:]
        return args

    def apply(self, head: Comp, args: Sequence[Entry], outs: Sequence[VType]) -> None:
        """`head` applied to `args` (pushed the deepest first), each boxed, its result bound to
        a fresh name and split into `outs`."""
        self.call(head, [self.boxed(a) for a in args], outs)

    def call(self, head: Comp, values: Sequence[IRValue], outs: Sequence[VType]) -> None:
        """`head` applied to `values`, pushed the deepest first, its result split into `outs`."""
        comp = _applied(head, values)
        result = self.name()
        self.lets.append(lambda rest: To(comp, result, "ω", rest))
        self.split(Var(result), outs)

    def boxed(self, entry: Entry) -> IRValue:
        """The entry as walker data: a thunk is boxed into its quotation."""
        value, t = entry
        if not isinstance(t, U):
            return value
        name = self.name()
        prim = Prim("box", instance([t], [Dyn()]), frozenset(), None)
        self.lets.append(lambda rest: To(App(value, prim), name, "ω", rest))
        return Var(name)

    def in_place(self, thunk: Entry, node: Call) -> None:
        """A thunk entry run on the top entries it takes, its results in their place."""
        value, t = thunk
        assert isinstance(t, U), t
        self.apply(Force(value), self.taken(len(inputs(t.comp)), node.span), results(t.comp))

    def wrapper(self, t: Entry, fresh: int, node: Call) -> Thunk:
        """`thunk (λx. … body)` over a fresh static stack of `fresh` names, `x` the top: `t` in
        place, returning the one entry it leaves, boxed; any other count is `STEP_ARITY`."""
        names = [self.name() for _ in range(fresh)]
        with self.aside([(Var(x), Dyn()) for x in reversed(names)]):
            self.in_place(t, node)
            if len(self.stack) != 1:
                left = f"{node.name} step leaves {len(self.stack)} values"
                raise _RefusalError(Refused(RefusalKind.STEP_ARITY, node.span, left))
            comp = _closed(self.lets, Return(self.boxed(self.stack[0])))
        for x in reversed(names):
            comp = Lam(x, Dyn(), "ω", comp)
        return Thunk(comp)

    def split(self, value: IRValue, outs: Sequence[VType]) -> None:
        """A right-nested pair of `outs` onto the static stack, one entry each."""
        if len(outs) == 1:
            self.stack.append((value, outs[0]))
        elif outs:
            left, right = self.name(), self.name()
            self.lets.append(lambda rest: SplitPair(value, left, "ω", right, "ω", rest))
            self.stack.append((Var(left), outs[0]))
            self.split(Var(right), outs[1:])

    def constant(self, prefix: str, fo: FirstOrder, args: Sequence[Entry]) -> None:
        """The program's own constant over `args` (the deepest first), one walker datum out."""
        name = f"{prefix}_{len(self.extra)}"
        self.extra.append((name, fo))
        ins = [Dyn() if isinstance(t, U) else t for _, t in reversed(args)]
        self.apply(Prim(name, instance(ins, [Dyn()]), frozenset(), None), args, [Dyn()])

    def arm(self, row: Row, taken: Sequence[Entry], env: Env) -> _Arm:
        """The row's test over the taken entries, the first pattern's the deepest, then its body
        on a fresh static stack with the names its patterns bind."""
        scope = dict(env)
        tests = [
            _PATTERNS[type(pattern)](self, pattern, entry, scope)
            for pattern, entry in zip(row.patterns, taken, strict=True)
        ]
        with self.aside([]):
            self.code(row.body, scope)
            return _Arm(
                self.both([t for t in tests if t is not None]), (*self.lets,), (*self.stack,)
            )

    def both(self, tests: Sequence[Comp]) -> Test:
        """The tests in turn, the first `inl` (false) ending them; None for no test."""
        if not tests:
            return None
        comp = tests[-1]
        for test in reversed(tests[:-1]):
            comp = self.chosen(test, Return(FALSE), comp)
        return comp

    def chosen(self, test: Comp, no: Comp, yes: Comp) -> Comp:
        """`test to b. pm b as {inl. no | inr. yes}`."""
        b = self.name()
        return To(test, b, "ω", Case(Var(b), self.name(), "ω", no, self.name(), "ω", yes))

    def same(self, start: list[Entry], code: tuple[Node, ...], env: Env, other: Entry) -> Comp:
        """`code` over the fresh static stack `start`, which must leave one entry, then `eq` of
        it and `other`: `inr` where the walker's `pattern.node == Push(value)` holds."""
        with self.aside(start):
            self.code(code, env)
            if len(self.stack) != 1:
                left = f"a pattern test leaves {len(self.stack)} values"
                raise _RefusalError(Refused(RefusalKind.EFFECT_MISMATCH, _spanned(code), left))
            args = [self.boxed(other), self.boxed(self.stack[0])]
            return _closed(self.lets, _applied(SAME, args))


def _push(low: _Lowering, node: Push, env: Env) -> None:
    value = node.value
    if isinstance(value, Quotation):
        low.stack.append(low.quotation(value, env))
        return
    mentioned = [x for x in env if substituted(value, x, PROBE) != value]
    if not mentioned:
        low.stack.append((Const(value, typed(value)), typed(value)))
        return
    # the outermost binder's entry goes on top, as `walker.held` takes it
    low.constant("held", held(value, mentioned), [env[x] for x in reversed(mentioned)])


def _call(low: _Lowering, node: Call, env: Env) -> None:
    if node.name in env:
        low.stack.append(env[node.name])
    elif node.name in low.queries:
        query = low.queries[node.name]
        low.stack.append((query, query.type))
    elif node.name in low.words:
        word = low.words[node.name]
        low.apply(Force(Var(node.name)), low.taken(word.ins, node.span), word.outs)
    else:
        _CALLS.get(node.name, _builtin)(low, node)


def _at(node: Call) -> Position:
    return Position(node.span.line, node.span.col)


def _builtin(low: _Lowering, node: Call) -> None:
    """`prim p` at its arguments' types; its 07 arrow types the results."""
    arrow = ARROWS[node.name]
    args = low.taken(len(arrow.ins), node.span)
    ins = [Dyn() if isinstance(t, U) else t for _, t in reversed(args)]
    outs = [ins[-1 - s.index] if isinstance(s, Input) else SORTS[s] for s in arrow.outs]
    low.apply(Prim(node.name, instance(ins, outs), frozenset(), _at(node)), args, outs)


def _inferred(_low: _Lowering, _node: Call) -> None:
    """`_` runs as nothing: 07 refuses one it cannot infer as nothing before the walker runs."""


def _goal(low: _Lowering, node: Call) -> None:
    low.apply(Prim(node.name, instance([], []), frozenset(), _at(node)), [], [])


def _in_place(low: _Lowering, node: Call, args: list[Entry]) -> None:
    low.stack.extend(args[:-1])
    low.in_place(args[-1], node)


def _iterated(low: _Lowering, node: Call, args: list[Entry]) -> None:
    """`prim w` applied to `xs` and the wrapper (the top), over one fresh name (two for scan and
    fold), its one result named."""
    xs, t = args
    fresh = 1 if node.name == "each" else 2
    wrapper = low.wrapper(t, fresh, node)
    eff = t[1].eff if isinstance(t[1], U) else frozenset[Eff]()
    shape = U(instance([Dyn()] * fresh, [Dyn()]), eff)
    prim = Prim(node.name, instance([shape, Dyn()], [Dyn()]), eff, _at(node))
    low.call(prim, [low.boxed(xs), wrapper], [Dyn()])


def _controlled(
    low: _Lowering, node: Call, args: list[Entry], run: Callable[..., None] = _in_place
) -> None:
    """A control word `run` on its thunk operand (the top), or refused: walker data may be
    anything, while a constant or a base value is statically not a quotation."""
    top, t = args[-1]
    if isinstance(t, U):
        run(low, node, args)
    elif isinstance(top, Const) or not isinstance(t, Dyn):
        prim = Prim(node.name, instance([Dyn()] * len(args), []), frozenset(), _at(node))
        low.extra.append((node.name, control(node.name)))
        low.apply(prim, args, [])
    else:
        why = f"{node.name} on walker data"
        raise _RefusalError(Refused(RefusalKind.QUOTATION_UNKNOWN, node.span, why))


def _force(low: _Lowering, node: Call) -> None:
    _controlled(low, node, low.taken(1, node.span))


def _commute(low: _Lowering, node: Call) -> None:
    """`x y t swap-args`: `t` in place on `y x`, as the walker's `commute` pushes them."""
    x, y, t = low.taken(3, node.span)
    _controlled(low, node, [y, x, t])


def _iterate(low: _Lowering, node: Call) -> None:
    _controlled(low, node, low.taken(2, node.span), _iterated)


_CALLS: dict[str, Callable[[_Lowering, Call], None]] = {
    "each": _iterate,
    "scan": _iterate,
    "fold": _iterate,
    "_": _inferred,
    "?": _goal,
    "!": _force,
    "swap-args": _commute,
}


def _bind(low: _Lowering, node: Bind, env: Env) -> None:
    """The top names `node.name` for the scope; the innermost binder of a name is the last."""
    (top,) = low.taken(1, node.span)
    inner = {x: e for x, e in env.items() if x != node.name}
    low.code(node.body, {**inner, node.name: top})


def _keyed(low: _Lowering, node: Keyed, env: Env) -> None:
    """Each entry's node on a fresh static stack, where it leaves one entry."""
    below, values = low.stack, list[Entry]()
    for _, entry in node.entries:
        low.stack = []
        low.code((entry,), env)
        values.extend(low.stack)
    low.stack = below
    low.constant("dict", keyed([k for k, _ in node.entries]), values)


def _spanned(code: tuple[Node, ...]) -> Span:
    """Where a pattern's test is written: its guard's call (the one test that may refuse)."""
    (node,) = code
    assert isinstance(node, Call), node
    return node.span


def _wild(_low: _Lowering, _pattern: Wild, _entry: Entry, _scope: dict[str, Entry]) -> Test:
    return None


def _named(_low: _Lowering, pattern: Named, entry: Entry, scope: dict[str, Entry]) -> Test:
    """The name stands for the entry in the patterns after it and in the body, innermost."""
    scope.pop(pattern.name, None)
    scope[pattern.name] = entry
    return None


def _equal(low: _Lowering, pattern: Equal, entry: Entry, scope: dict[str, Entry]) -> Test:
    return low.same([], (pattern.node,), scope, entry)


def _guarded(low: _Lowering, pattern: Guarded, entry: Entry, scope: dict[str, Entry]) -> Test:
    """The guarded pattern's test, then the guard's word on the entry alone, compared with 1;
    the guard runs even when the pattern failed, as in the walker's `matched`."""
    inner = _PATTERNS[type(pattern.pattern)](low, pattern.pattern, entry, scope)
    guard = low.same([entry], (Call(pattern.test, pattern.span),), {}, ONE)
    if inner is None:
        return guard
    passed, held = low.name(), low.name()
    pick = Case(Var(passed), low.name(), "ω", Return(FALSE), low.name(), "ω", Return(Var(held)))
    return To(inner, passed, "ω", To(guard, held, "ω", pick))


def _inverse(_low: _Lowering, pattern: Inverse, _entry: Entry, _scope: dict[str, Entry]) -> Test:
    raise _RefusalError(Refused(RefusalKind.INVERSE_PATTERN, pattern.span, "refused by pass 1"))


_PATTERNS: dict[type, Callable[..., Test]] = {
    Wild: _wild,
    Named: _named,
    Equal: _equal,
    Guarded: _guarded,
    Inverse: _inverse,
}


def _match(low: _Lowering, node: Match, env: Env) -> None:
    """The rows tried in order up to the first catching every value, the last falling into
    `fail` without one; what the chosen row leaves is bound by one `to` and split."""
    taken = low.taken(len(node.rows[0].patterns), node.span)
    arms: list[_Arm] = []
    for row in node.rows:
        arms.append(low.arm(row, taken, env))
        if arms[-1].test is None:
            break
    types = _joined(arms, node.span)
    last = arms[-1]
    comp: Comp = Fail(Const(FplError(node.span, "no row matches"), Dyn()))
    if last.test is None:
        comp = _body(arms.pop())
    for arm in reversed(arms):
        assert arm.test is not None
        comp = low.chosen(arm.test, comp, _body(arm))
    result = low.name()
    low.lets.append(lambda rest: To(comp, result, "ω", rest))
    low.split(Var(result), types)


def _body(arm: _Arm) -> Comp:
    return _closed(arm.lets, Return(paired([v for v, _ in arm.stack])))


def _joined(arms: Sequence[_Arm], at: Span) -> list[VType]:
    """The types of the entries every row leaves: one type, or base types and `Dyn` with at most
    one base among them, as `Dyn`; refused where the rows leave different counts or no such type
    exists, which the checker's `pm` would not join."""
    counts = {len(arm.stack) for arm in arms}
    if len(counts) != 1:
        raise _RefusalError(
            Refused(RefusalKind.BRANCHES_DISAGREE, at, f"rows leave {sorted(counts)} values")
        )
    return [_fit(column, at) for column in zip(*(arm.stack for arm in arms), strict=True)]


def _fit(column: Sequence[Entry], at: Span) -> VType:
    """The one type of the entries the rows leave in one place, `Dyn` for base types and `Dyn`
    with at most one base among them; refused otherwise."""
    kinds = {t for _, t in column}
    if len(kinds) == 1:
        return kinds.pop()
    if all(isinstance(t, Base | Dyn) for t in kinds) and len(kinds - {Dyn()}) <= 1:
        return Dyn()
    raise _RefusalError(Refused(RefusalKind.BRANCHES_DISAGREE, at, f"rows leave {kinds}"))


_NODES: dict[type, Callable[..., None]] = {
    Push: _push,
    Call: _call,
    Bind: _bind,
    Keyed: _keyed,
    Match: _match,
}


@icontract.require(lowerable)
def polarise(core: CoreA) -> Lowered | Refused:
    """The cbpv⁻ program for Core_A, the constants of its own it uses (for `walker.signature`)
    and its literal quotations' origins (for `walker.readback`); or the first refusal."""
    low = _Lowering()
    low.extra.append(("box", box(low.origins)))
    try:
        defs = tuple((s.name, low.word(s)) for s in core.statements if isinstance(s, Define))
        runs: list[Comp] = []
        for statement in core.statements:
            if not isinstance(statement, Define):
                low.stack = []
                runs.append(low.body(statement.code)[0])
    except _RefusalError as refusal:
        return refusal.refused
    return Program(defs, tuple(runs)), tuple(low.extra), tuple(low.origins)
