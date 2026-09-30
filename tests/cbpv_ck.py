"""The statement's CK machine, transcribed literally: the oracle for `fpl.cbpv.machine`.

A state is `⟨M, K⟩`: a closed computation and a stack, a tuple (top first) of the statement's
frames `("arg", V)` for `V :: K`, `("to", x, N)`, `("fst",)`, `("snd",)`, and the design's
`("loop", p, s)` (section 5). β substitutes, `M[V/x]`; only closed values are ever substituted,
so substitution stops at a binder of the same name and never renames: it avoids capture because
nothing it inserts has a free variable. One function per rule. The conventions are the
machine's: a rule that applies is a step, `fail` and a panic included; `return V` and `λx. M` on
the empty stack end the run without one. For the constant and loop rows this checks the design
against itself; only the walker differential is independent there.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, fields, is_dataclass, replace
from typing import Any

from fpl.cbpv.sig import Done, FirstOrder, Iterating, Panic, Signature, Step
from fpl.cbpv.syntax import (
    App,
    Both,
    Case,
    Comp,
    Const,
    Fail,
    First,
    Force,
    Inl,
    Inr,
    Label,
    Lam,
    Op,
    Pair,
    Prim,
    Program,
    Rec,
    Return,
    Second,
    SplitPair,
    Thunk,
    To,
    Value,
    Var,
)

type Stack = tuple[tuple[Any, ...], ...]
type Outcome = tuple[tuple[Any, ...], tuple[tuple[Any, ...], ...], int]
BINDS: dict[type, dict[str, tuple[str, ...]]] = {
    Lam: {"body": ("name",)},
    To: {"body": ("name",)},
    Rec: {"body": ("name",)},
    SplitPair: {"body": ("left", "right")},
    Case: {"left": ("left_name",), "right": ("right_name",)},
}


def subst(x: Any, sub: Mapping[str, Value]) -> Any:
    """`x[sub]`: each free occurrence of a name `sub` maps replaced by its closed value."""
    if isinstance(x, Var):
        return sub.get(x.name, x)
    if not sub or not is_dataclass(x) or isinstance(x, type):
        return x
    binds = BINDS.get(type(x), {})

    def under(name: str) -> Mapping[str, Value]:
        shadowed = {getattr(x, n) for n in binds.get(name, ())}
        return {k: v for k, v in sub.items() if k not in shadowed}

    return replace(x, **{f.name: subst(getattr(x, f.name), under(f.name)) for f in fields(x)})


@dataclass
class Machine:
    """The signature, the handler that answers `op`, and the events so far."""

    sig: Signature
    handler: Callable[[str, Any, Any], Any]
    trace: list[tuple[Any, ...]] = field(default_factory=list[tuple[Any, ...]])


@dataclass(frozen=True)
class Ended:
    """A rule ended the run: `("failed", W)` or `("panicked", payload, at)`."""

    view: tuple[Any, ...]


type Next = tuple[Comp, Stack] | Ended


def ck_run(
    program: Program, sig: Signature, handler: Callable[[str, Any, Any], Any]
) -> list[Outcome]:
    """Each run: its end (`("returned", V)`, `("unsaturated", thunk λ)`, `("failed", W)`,
    `("panicked", payload, at)`), its events (`("op", op, V, W, r)`, `("label", l)`), steps."""
    defs: dict[str, Value] = {}
    for name, value in program.defs:
        defs[name] = subst(value, defs)
    return [_run(subst(m, defs), Machine(sig, handler)) for m in program.runs]


def _run(m: Comp, ck: Machine) -> Outcome:
    k: Stack = ()
    steps = 0
    while True:
        if not k and isinstance(m, Return):
            return ("returned", m.value), tuple(ck.trace), steps
        if not k and isinstance(m, Lam):
            return ("unsaturated", Thunk(m)), tuple(ck.trace), steps
        after = RULES[type(m)](m, k, ck)
        steps += 1
        if isinstance(after, Ended):
            return after.view, tuple(ck.trace), steps
        m, k = after


def _app(m: App, k: Stack, _ck: Machine) -> Next:
    return m.fun, (("arg", m.arg), *k)


def _lam(m: Lam, k: Stack, _ck: Machine) -> Next:
    assert k[0][0] == "arg"
    return subst(m.body, {m.name: k[0][1]}), k[1:]


def _to(m: To, k: Stack, _ck: Machine) -> Next:
    return m.bound, (("to", m.name, m.body), *k)


def _return(m: Return, k: Stack, ck: Machine) -> Next:
    if k[0][0] == "to":
        return subst(k[0][2], {k[0][1]: m.value}), k[1:]
    _, p, state = k[0]
    constant = ck.sig.constants[p.name]
    assert isinstance(constant, Iterating)
    return _iterate(p, constant.resume(state, m.value), k[1:])


def _force(m: Force, k: Stack, _ck: Machine) -> Next:
    assert isinstance(m.value, Thunk)
    return m.value.body, k


def _split(m: SplitPair, k: Stack, _ck: Machine) -> Next:
    assert isinstance(m.value, Pair)
    return subst(m.body, {m.left: m.value.left, m.right: m.value.right}), k


def _case(m: Case, k: Stack, _ck: Machine) -> Next:
    if isinstance(m.value, Inl):
        return subst(m.left, {m.left_name: m.value.value}), k
    assert isinstance(m.value, Inr)
    return subst(m.right, {m.right_name: m.value.value}), k


def _both(m: Both, k: Stack, _ck: Machine) -> Next:
    return (m.left if k[0] == ("fst",) else m.right), k[1:]


def _first(m: First, k: Stack, _ck: Machine) -> Next:
    return m.comp, (("fst",), *k)


def _second(m: Second, k: Stack, _ck: Machine) -> Next:
    return m.comp, (("snd",), *k)


def _rec(m: Rec, k: Stack, _ck: Machine) -> Next:
    return subst(m.body, {m.name: Thunk(m)}), k


def _op(m: Op, k: Stack, ck: Machine) -> Next:
    result = ck.handler(m.op, m.cap, m.arg)
    ck.trace.append(("op", m.op, m.cap, m.arg, result))
    return Return(result), k


def _fail(m: Fail, _k: Stack, _ck: Machine) -> Next:
    return Ended(("failed", m.payload))


def _label(m: Label, k: Stack, ck: Machine) -> Next:
    ck.trace.append(("label", m.label))
    return m.body, k


def _prim(m: Prim, k: Stack, ck: Machine) -> Next:
    constant = ck.sig.constants[m.name]
    args, rest = tuple(frame[1] for frame in k[: constant.arity]), k[constant.arity :]
    assert all(frame[0] == "arg" for frame in k[: constant.arity])
    if isinstance(constant, FirstOrder):
        result = constant.apply(tuple(a.value if isinstance(a, Const) else a for a in args), m.at)
        if isinstance(result, Panic):
            return Ended(("panicked", result.payload, m.at))
        return Return(result), rest
    return _iterate(m, constant.start(args, m.at), rest)


def _iterate(p: Prim, step: Step | Panic, rest: Stack) -> Next:
    if isinstance(step, Panic):
        return Ended(("panicked", step.payload, p.at))
    if isinstance(step, Done):
        return Return(step.value), rest
    return Force(step.thunk), (*(("arg", a) for a in step.args), ("loop", p, step.state), *rest)


RULES: dict[type, Callable[[Any, Stack, Machine], Next]] = {
    App: _app,
    Lam: _lam,
    To: _to,
    Return: _return,
    Force: _force,
    SplitPair: _split,
    Case: _case,
    Both: _both,
    First: _first,
    Second: _second,
    Rec: _rec,
    Op: _op,
    Fail: _fail,
    Label: _label,
    Prim: _prim,
}
