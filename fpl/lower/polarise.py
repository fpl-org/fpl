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

Refused, by precondition: a match, a control word, a word calling itself or in a component of
more than one word. Those lower in later passes (holes static-stack, effect-mismatch).
"""

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import count

import icontract

from fpl.ast_core import Bind, Call, Define, Keyed, Match, Node, Push, Symbol
from fpl.cbpv.sig import FirstOrder
from fpl.cbpv.syntax import (
    App,
    Comp,
    Const,
    Dyn,
    Force,
    Lam,
    Position,
    Prim,
    Program,
    Return,
    SplitPair,
    Thunk,
    To,
    Var,
    VType,
)
from fpl.cbpv.syntax import Value as IRValue
from fpl.eval import CONTROLS, effect_line
from fpl.eval import held as substituted
from fpl.lower.select import CoreA
from fpl.lower.walker import SORTS, held, instance, keyed, paired, typed
from fpl.types import ARROWS, Input

type Entry = tuple[IRValue, VType]
type Env = Mapping[str, Entry]
type Extra = tuple[tuple[str, FirstOrder], ...]

PROBE = Symbol("probe")  # stands in for a binder while looking for its mentions
OFF = frozenset(CONTROLS)


def _flat(code: tuple[Node, ...]) -> Iterator[Node]:
    """Every node of `code`, through binder scopes and dict entries (quotations are data)."""
    for node in code:
        yield node
        if isinstance(node, Bind):
            yield from _flat(node.body)
        elif isinstance(node, Keyed):
            yield from _flat(tuple(n for _, n in node.entries))


def _off(node: Node, own: str) -> bool:
    return isinstance(node, Match) or (isinstance(node, Call) and node.name in OFF | {own})


def straight_line(core: CoreA) -> bool:
    """No match, control word or hole, no word calling itself, one word per component."""
    owned = ((s.name if isinstance(s, Define) else "", s.code) for s in core.statements)
    plain = not any(_off(node, own) for own, code in owned for node in _flat(code))
    return plain and all(len(c) == 1 for c in core.components)


@dataclass
class _Lowering:
    """The words lowered so far (inputs, output types), the queries they answer, the program's
    own constants, and the static stack and pending bindings of the code being lowered."""

    words: dict[str, tuple[int, tuple[VType, ...]]] = field(
        default_factory=dict[str, tuple[int, tuple[VType, ...]]]
    )
    queries: dict[str, Const] = field(default_factory=dict[str, Const])
    extra: list[tuple[str, FirstOrder]] = field(default_factory=list[tuple[str, FirstOrder]])
    stack: list[Entry] = field(default_factory=list[Entry])
    lets: list[Callable[[Comp], Comp]] = field(default_factory=list[Callable[[Comp], Comp]])
    fresh: Iterator[int] = field(default_factory=count)

    def name(self) -> str:
        """An IR name no walker word can spell: it holds a space."""
        return f" v{next(self.fresh)}"

    def code(self, code: tuple[Node, ...], env: Env) -> None:
        for node in code:
            _NODES[type(node)](self, node, env)

    def body(self, code: tuple[Node, ...]) -> tuple[Comp, tuple[VType, ...]]:
        """`code` over the static stack, returning the entries it leaves, and their types."""
        self.lets = []
        self.code(code, {})
        comp: Comp = Return(paired([v for v, _ in self.stack]))
        for let in reversed(self.lets):
            comp = let(comp)
        return comp, tuple(t for _, t in self.stack)

    def word(self, define: Define) -> Thunk:
        """`thunk (λtop. … λdeepest. body)`; its inputs are walker data (`Dyn`)."""
        names = [self.name() for _ in define.effect.ins]
        self.stack = [(Var(x), Dyn()) for x in reversed(names)]
        comp, outs = self.body(define.code)
        for x in reversed(names):
            comp = Lam(x, Dyn(), "ω", comp)
        self.words[define.name] = (len(names), outs)
        self.queries[f"{define.name}/doc"] = Const(define.doc, typed(define.doc))
        self.queries[f"{define.name}/effect"] = Const(effect_line(define), Dyn())
        return Thunk(comp)

    def taken(self, n: int) -> list[Entry]:
        """The top `n` entries, the deepest first, popped."""
        cut = len(self.stack) - n
        args = self.stack[cut:]
        del self.stack[cut:]
        return args

    def apply(self, head: Comp, args: Sequence[Entry], outs: Sequence[VType]) -> None:
        """`head` applied to `args` (pushed the deepest first), its result bound to a fresh name
        and split into `outs`."""
        comp = head
        for value, _ in reversed(args):
            comp = App(value, comp)
        result = self.name()
        self.lets.append(lambda rest: To(comp, result, "ω", rest))
        self.split(Var(result), outs)

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
        prim = Prim(name, instance([t for _, t in reversed(args)], [Dyn()]), frozenset(), None)
        self.apply(prim, args, [Dyn()])


def _push(low: _Lowering, node: Push, env: Env) -> None:
    value = node.value
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
        n, outs = low.words[node.name]
        low.apply(Force(Var(node.name)), low.taken(n), outs)
    else:
        _CALLS.get(node.name, _builtin)(low, node)


def _at(node: Call) -> Position:
    return Position(node.span.line, node.span.col)


def _builtin(low: _Lowering, node: Call) -> None:
    """`prim p` at its arguments' types; its 07 arrow types the results."""
    arrow = ARROWS[node.name]
    args = low.taken(len(arrow.ins))
    outs = [args[s.index][1] if isinstance(s, Input) else SORTS[s] for s in arrow.outs]
    ins = [t for _, t in reversed(args)]
    low.apply(Prim(node.name, instance(ins, outs), frozenset(), _at(node)), args, outs)


def _inferred(_low: _Lowering, _node: Call) -> None:
    """`_` runs as nothing: 07 refuses one it cannot infer as nothing before the walker runs."""


def _goal(low: _Lowering, node: Call) -> None:
    low.apply(Prim(node.name, instance([], []), frozenset(), _at(node)), [], [])


_CALLS: dict[str, Callable[[_Lowering, Call], None]] = {"_": _inferred, "?": _goal}


def _bind(low: _Lowering, node: Bind, env: Env) -> None:
    """The top names `node.name` for the scope; the innermost binder of a name is the last."""
    top = low.stack.pop()
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


_NODES: dict[type, Callable[..., None]] = {
    Push: _push,
    Call: _call,
    Bind: _bind,
    Keyed: _keyed,
}


@icontract.require(straight_line)
def polarise(core: CoreA) -> tuple[Program, Extra]:
    """The cbpv⁻ program for straight-line Core_A, and the constants of its own it uses (for
    `walker.signature`)."""
    low = _Lowering()
    defs = tuple((s.name, low.word(s)) for s in core.statements if isinstance(s, Define))
    runs: list[Comp] = []
    for statement in core.statements:
        if not isinstance(statement, Define):
            low.stack = []
            runs.append(low.body(statement.code)[0])
    return Program(defs, tuple(runs)), tuple(low.extra)
