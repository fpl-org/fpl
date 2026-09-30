"""Pass 1, select: the core AST a program's run lines reach, as Core_A (design section 6.1).

Promised: `select` keeps each word's last definition that a run line reaches, through calls
in code and in the quotations and lists it pushes, and every run line; it drops earlier
definitions and those nothing reaches, which the walker never runs either. A call resolves as
`fpl.eval.step` resolves it: an enclosing binder (a `Bind`, or a name a match row binds),
then a defined word or a query over one, then a builtin or control word. The definitions come
in the order of the call graph's strongly connected components, the ones a component calls
first. A reachable `f/doc` or `f/effect` keeps `f`.

Refused, as a `Refused` value and never an exception: code as data (`,`, a `code` slot,
`name/history`: `LEVEL_ONE`, hole level-one), and a binder whose name some reachable call
outside its scope resolves to a word or builtin (`BINDER_CAPTURES`, hole binder-captures): the
walker substitutes into quotation values a binder put into its scope, A resolves lexically.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from graphlib import TopologicalSorter

from fpl.ast_core import (
    Bind,
    Call,
    Define,
    Equal,
    Guarded,
    Inverse,
    Keyed,
    Listed,
    Match,
    Node,
    Push,
    Quotation,
    Run,
    Statement,
    Value,
    Var,
    Wild,
)
from fpl.errors import Span
from fpl.eval import names
from fpl.types import QUERIES


class RefusalKind(StrEnum):
    """What a pass refuses to lower, each with its hole in HOLES.md."""

    LEVEL_ONE = "level-one"
    BINDER_CAPTURES = "binder-captures"
    QUOTATION_UNKNOWN = "quotation-unknown"
    EFFECT_MISMATCH = "effect-mismatch"
    STEP_ARITY = "step-stack"


@dataclass(frozen=True)
class Refused:
    """A pass's refusal: its kind, where in the source, and why."""

    kind: RefusalKind
    at: Span
    detail: str


@dataclass(frozen=True)
class CoreA:
    """The reachable definitions, components in dependency order, then every run line."""

    statements: tuple[Statement, ...]
    components: tuple[tuple[str, ...], ...]


type Env = frozenset[str]
type Graph = Mapping[str, tuple[str, ...]]


@dataclass
class _Walk:
    """The calls met so far, each with what it resolves to (None: a binder, "": a builtin or
    control word, else the word or query called), and the binders met."""

    words: Mapping[str, tuple[str, str]]
    calls: list[tuple[Call, str | None]] = field(default_factory=list[tuple[Call, str | None]])
    binders: list[tuple[str, Span]] = field(default_factory=list[tuple[str, Span]])

    def code(self, code: tuple[Node, ...], env: Env) -> None:
        for node in code:
            _NODES[type(node)](self, node, env)

    def owners(self, start: int) -> tuple[str, ...]:
        """The definitions the calls from `start` on reach."""
        return tuple(dict.fromkeys(self.words[t][0] for _, t in self.calls[start:] if t))


def _push(walk: _Walk, node: Push, env: Env) -> None:
    _value(walk, node.value, env)


def _value(walk: _Walk, value: Value, env: Env) -> None:
    """A pushed value's code: a binder's substitution reaches quotations and lists."""
    if isinstance(value, Quotation):
        walk.code(value.code, env)
    elif isinstance(value, Listed):
        for item in value.items:
            _value(walk, item, env)


def _call(walk: _Walk, node: Call, env: Env) -> None:
    target = None if node.name in env else node.name if node.name in walk.words else ""
    walk.calls.append((node, target))


def _bind(walk: _Walk, node: Bind, env: Env) -> None:
    walk.binders.append((node.name, node.span))
    walk.code(node.body, env | {node.name})


def _keyed(walk: _Walk, node: Keyed, env: Env) -> None:
    walk.code(tuple(n for _, n in node.entries), env)


def _match(walk: _Walk, node: Match, env: Env) -> None:
    for row in node.rows:
        bound = frozenset[str]().union(*map(names, row.patterns))
        walk.binders.extend((name, node.span) for name in sorted(bound))
        for pattern in row.patterns:
            _PATTERNS[type(pattern)](walk, pattern, env)
        walk.code(row.body, env | bound)


def _equal(walk: _Walk, pattern: Equal, env: Env) -> None:
    walk.code((pattern.node,), env)


def _guarded(walk: _Walk, pattern: Guarded, env: Env) -> None:
    _PATTERNS[type(pattern.pattern)](walk, pattern.pattern, env)
    _call(walk, Call(pattern.test, pattern.span), frozenset())


def _inverse(walk: _Walk, pattern: Inverse, env: Env) -> None:
    for arg in pattern.args:
        _PATTERNS[type(arg)](walk, arg, env)
    _call(walk, Call(pattern.name, pattern.span), frozenset())


def _nothing(_walk: _Walk, _pattern: Wild | Var, _env: Env) -> None:
    """A wildcard or a name tests nothing and calls nothing."""


_NODES: dict[type, Callable[..., None]] = {
    Push: _push,
    Call: _call,
    Bind: _bind,
    Keyed: _keyed,
    Match: _match,
}
_PATTERNS: dict[type, Callable[..., None]] = {
    Wild: _nothing,
    Var: _nothing,
    Equal: _equal,
    Guarded: _guarded,
    Inverse: _inverse,
}


def callables(defines: Mapping[str, Define]) -> dict[str, tuple[str, str]]:
    """Each name a call may resolve to a word by, with its definition and query ("" for none);
    a query shadows a word spelled the same, as in `fpl.eval.evaluate`."""
    words = {name: (name, "") for name in defines}
    words.update({f"{name}/{q}": (name, q) for name in defines for q in QUERIES})
    return words


def select(statements: tuple[Statement, ...]) -> CoreA | Refused:
    """Core_A for `statements`, or the first refusal."""
    defines = {s.name: s for s in statements if isinstance(s, Define)}
    runs = tuple(s for s in statements if isinstance(s, Run))
    walk = _Walk(callables(defines))
    walk.code(sum((run.code for run in runs), ()), frozenset())
    graph = _called(walk, defines)
    refused = _level_one(walk, list(map(defines.__getitem__, sorted(graph))))
    return refused or _captures(walk) or _ordered(defines, graph, runs)


def _ordered(defines: Mapping[str, Define], graph: Graph, runs: tuple[Run, ...]) -> CoreA:
    """The definitions reached, in component order, then the run lines."""
    order = components(graph)
    return CoreA((*(defines[n] for c in order for n in c), *runs), order)


def _called(walk: _Walk, defines: Mapping[str, Define]) -> dict[str, tuple[str, ...]]:
    """The call graph of the definitions the calls walked so far reach, walking each once."""
    graph: dict[str, tuple[str, ...]] = {}
    todo = list(walk.owners(0))
    while todo:
        name = todo.pop()
        if name not in graph:
            start = len(walk.calls)
            walk.code(defines[name].code, frozenset())
            graph[name] = walk.owners(start)
            todo.extend(graph[name])
    return graph


def _level_one(walk: _Walk, reached: list[Define]) -> Refused | None:
    """The first code-as-data construct reached: `,`, `name/history`, a `code` slot."""
    for call, target in walk.calls:
        if (target == "" and call.name == ",") or (target and walk.words[target][1] == "history"):
            return Refused(RefusalKind.LEVEL_ONE, call.span, f"{call.name} makes code a value")
    for define in reached:
        if "code" in define.effect.slots:
            return Refused(RefusalKind.LEVEL_ONE, define.span, f"{define.name} takes code")
    return None


def _captures(walk: _Walk) -> Refused | None:
    """The first binder whose name a call outside its scope resolves to a word or builtin."""
    free = {call.name for call, target in walk.calls if target is not None}
    for name, at in walk.binders:
        if name in free:
            detail = f"{name} is also called outside this binder's scope"
            return Refused(RefusalKind.BINDER_CAPTURES, at, detail)
    return None


def components(graph: Graph) -> tuple[tuple[str, ...], ...]:
    """The strongly connected components of `graph`, each sorted, the ones a component calls
    before it."""
    comp = _condensed(graph)
    deps: dict[tuple[str, ...], dict[tuple[str, ...], None]] = {comp[n]: {} for n in sorted(graph)}
    for n in sorted(graph):
        deps[comp[n]].update(dict.fromkeys(comp[m] for m in graph[n]))
        deps[comp[n]].pop(comp[n], None)
    return tuple(TopologicalSorter(deps).static_order())


def _condensed(graph: Graph) -> dict[str, tuple[str, ...]]:
    """Each word's component: the words it reaches that reach it back, and itself. Quadratic in
    the words reached (a reachability set per word), which programs keep small."""
    reach = {n: _reached(n, graph) for n in graph}
    mutual = {n: {m for m in reach[n] if n in reach[m]} | {n} for n in graph}
    return {n: tuple(sorted(mutual[n])) for n in graph}


def _reached(start: str, graph: Graph) -> frozenset[str]:
    """The words `start` reaches through one call or more."""
    seen: set[str] = set()
    todo = list(graph[start])
    while todo:
        name = todo.pop()
        if name not in seen:
            seen.add(name)
            todo.extend(graph[name])
    return frozenset(seen)


def in_core_a(statements: tuple[Statement, ...]) -> bool:
    """Core_A is what `select` leaves unchanged: every definition reached, once, in component
    order, and nothing refused."""
    selected = select(statements)
    return isinstance(selected, CoreA) and selected.statements == statements
