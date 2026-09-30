"""Typing for the IR: Levy's rules with the statement's three additions (design section 4).

`check(program, sig, loops=...)` returns `None` when every definition is a closed value over
those before it and every run a closed computation of type `F A`, and otherwise the first
`TypeError_`, whose `where` is the path of field indices to the offending node (definition
`i`'s value at `(0, i, 1)`, run `j` at `(1, j)`). It never raises on a program.

Choices the statement leaves open, each a hole in HOLES.md: a thunk's latent effect lives on
`U` (thunk-effect); `Dyn` is consistent with base types and nothing else (dynamic-sort); `op`
wants its capability and argument at their exact types (op-typing); `fail W` has every
computation type, written `Bottom` here, with `W` at the signature's payload type
(fail-payload); `⟨M, N⟩` has both halves' effects (with-effects); a constant is admitted per
instance by the signature (prim-instances). Of the grades only 0 is enforced (grades). `0`
fits every value type, so a `to` after `fail` binds a variable of type `0`. With
`loops=True`, every `rec` body leads with a label, and so does every thunk an iterating
constant receives in its application spine, which must be a thunk literal.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import StrEnum, auto
from typing import Any, NoReturn

from fpl.cbpv.sig import FirstOrder, Iterating, Signature
from fpl.cbpv.syntax import (
    Absurd,
    App,
    Arrow,
    Base,
    Both,
    Case,
    Comp,
    Const,
    CType,
    Dyn,
    Effects,
    F,
    Fail,
    First,
    Force,
    Grade,
    Inl,
    Inr,
    Label,
    Lam,
    One,
    Op,
    Pair,
    Prim,
    Prod,
    Program,
    Rec,
    Return,
    Second,
    SplitPair,
    Sum,
    Thunk,
    To,
    Top,
    Type,
    U,
    Unit,
    Value,
    Var,
    VType,
    With,
    Zero,
)

type Path = tuple[int, ...]
PURE: Effects = frozenset()


class TypeErrorKind(StrEnum):
    """Why a program does not type; `invalid()` holds one mutation per kind."""

    UNBOUND = auto()
    MISMATCH = auto()
    NOT_THUNK = auto()
    NOT_FUNCTION = auto()
    NOT_RETURNER = auto()
    NOT_PAIR = auto()
    NOT_SUM = auto()
    NOT_WITH = auto()
    EFFECT_ESCAPES = auto()
    REC_WITHOUT_DIV = auto()
    GRADE_ZERO_USED = auto()
    PRIM_INSTANCE = auto()
    OP_UNKNOWN = auto()
    LOOP_UNLABELLED = auto()


@dataclass(frozen=True, slots=True)
class TypeError_:  # noqa: N801 -- the design's name; the builtin TypeError stays unshadowed
    """The first refusal: its kind, the path of field indices to the node, and a message."""

    kind: TypeErrorKind
    where: Path
    detail: str


@dataclass(frozen=True, slots=True)
class Bottom(Top):
    """The type of `fail W`: it fits every computation type. A `Top` only so a thunk of it is a
    `U`; the checker makes it, and no program mentions it."""


class _RefusedError(Exception):
    """Unwinds the checker to `check` with the first refusal."""

    def __init__(self, error: TypeError_) -> None:
        super().__init__(error.detail)
        self.error = error


@dataclass(frozen=True, slots=True)
class _Env:
    """The signature, the variables in scope with their types and grades, and where we are."""

    sig: Signature
    scope: Mapping[str, tuple[VType, Grade]]
    path: Path

    def at(self, *index: int) -> _Env:
        return _Env(self.sig, self.scope, (*self.path, *index))

    def bind(self, name: str, vtype: VType, grade: Grade) -> _Env:
        return _Env(self.sig, {**self.scope, name: (vtype, grade)}, self.path)

    def refuse(self, kind: TypeErrorKind, detail: str) -> NoReturn:
        raise _RefusedError(TypeError_(kind, self.path, detail))

    def fit(self, got: Type, want: Type) -> None:
        kind = fits(got, want)
        if kind is not None:
            self.refuse(kind, f"{got!r} does not fit {want!r}")


def check(program: Program, sig: Signature, *, loops: bool) -> TypeError_ | None:
    """`None` if `program` types under `sig` (and, with `loops`, labels every loop body)."""
    try:
        _program(program, sig)
    except _RefusedError as refused:
        return refused.error
    where = _unlabelled(program, sig, ()) if loops else None
    if where is None:
        return None
    return TypeError_(TypeErrorKind.LOOP_UNLABELLED, where, "a loop body without a label")


def _program(program: Program, sig: Signature) -> None:
    scope: Mapping[str, tuple[VType, Grade]] = {}
    for i, (name, value) in enumerate(program.defs):
        scope = {**scope, name: (_value(value, _Env(sig, scope, (0, i, 1))), "ω")}
    for j, run in enumerate(program.runs):
        env = _Env(sig, scope, (1, j))
        result, _ = _comp(run, env)
        if not isinstance(result, F | Bottom):
            env.refuse(TypeErrorKind.NOT_RETURNER, f"a run of type {result!r}")


# Subsumption and consistency.


def fits(got: Type, want: Type) -> TypeErrorKind | None:
    """`None` when a `got` may stand where a `want` is wanted: `Dyn` is consistent with base
    types, `U_ε B` fits `U_ε' B'` when `ε ⊆ ε'` and `B` fits `B'`, arrows are contravariant
    in their argument, and `0` and `Bottom` fit everything."""
    if isinstance(got, Zero | Bottom) or _consistent(got, want):
        return None
    if type(got) is not type(want):
        return TypeErrorKind.MISMATCH
    return _FITS[type(got)](got, want)


def _consistent(got: Type, want: Type) -> bool:
    return isinstance(got, Base | Dyn) and isinstance(want, Base | Dyn) and Dyn() in (got, want)


def _fits_base(got: Base, want: Base) -> TypeErrorKind | None:
    return None if got.name == want.name else TypeErrorKind.MISMATCH


def _fits_halves(got: Prod | Sum | With, want: Prod | Sum | With) -> TypeErrorKind | None:
    return fits(got.left, want.left) or fits(got.right, want.right)


def _fits_u(got: U, want: U) -> TypeErrorKind | None:
    escapes = None if got.eff <= want.eff else TypeErrorKind.EFFECT_ESCAPES
    return fits(got.comp, want.comp) or escapes


def _fits_f(got: F, want: F) -> TypeErrorKind | None:
    return fits(got.value, want.value)


def _fits_arrow(got: Arrow, want: Arrow) -> TypeErrorKind | None:
    return fits(want.arg, got.arg) or fits(got.res, want.res)


def _fits_unit(_got: Type, _want: Type) -> TypeErrorKind | None:
    return None


_FITS: dict[type, Callable[[Any, Any], TypeErrorKind | None]] = {
    Base: _fits_base,
    One: _fits_unit,
    Top: _fits_unit,
    Prod: _fits_halves,
    Sum: _fits_halves,
    With: _fits_halves,
    U: _fits_u,
    F: _fits_f,
    Arrow: _fits_arrow,
}


def _widen(a: Any, b: Any) -> Any:
    """A type both fit when they differ only in the effects on `U`, else `a` (which the caller
    then finds does not fit)."""
    if isinstance(a, Zero | Bottom):
        return b
    if type(a) is not type(b) or not isinstance(a, U | F | Prod | Sum | Arrow | With):
        return a
    wider = {f.name: _widen(getattr(a, f.name), getattr(b, f.name)) for f in fields(a)}
    if isinstance(a, U):
        wider["eff"] = a.eff | b.eff
    return replace(a, **wider)


# Values: each rule returns the value's type.


def _value(v: Value, env: _Env) -> VType:
    return _VALUES[type(v)](v, env)


def _var(v: Var, env: _Env) -> VType:
    if v.name not in env.scope:
        env.refuse(TypeErrorKind.UNBOUND, v.name)
    vtype, grade = env.scope[v.name]
    if grade == 0:
        env.refuse(TypeErrorKind.GRADE_ZERO_USED, v.name)
    return vtype


def _const(v: Const, env: _Env) -> VType:
    based = isinstance(v.type, Base) and v.type.name in env.sig.bases
    if not (based or isinstance(v.type, Dyn)):
        env.refuse(TypeErrorKind.MISMATCH, f"a literal at {v.type!r}, not a base type")
    return v.type


def _pair(v: Pair, env: _Env) -> VType:
    return Prod(_value(v.left, env.at(0)), _value(v.right, env.at(1)))


def _inl(v: Inl, env: _Env) -> VType:
    return Sum(_value(v.value, env.at(0)), v.right)


def _inr(v: Inr, env: _Env) -> VType:
    return Sum(v.left, _value(v.value, env.at(0)))


def _thunk(v: Thunk, env: _Env) -> VType:
    body, eff = _comp(v.body, env.at(0))
    return U(body, eff)


_VALUES: dict[type, Callable[[Any, _Env], VType]] = {
    Var: _var,
    Const: _const,
    Unit: lambda _v, _env: One(),
    Pair: _pair,
    Inl: _inl,
    Inr: _inr,
    Thunk: _thunk,
}


# Computations: each rule returns the computation's type and effect.

type Judged = tuple[CType, Effects]


def _comp(m: Comp, env: _Env) -> Judged:
    return _COMPS[type(m)](m, env)


def _judge_return(m: Return, env: _Env) -> Judged:
    return F(_value(m.value, env.at(0))), PURE


def _judge_to(m: To, env: _Env) -> Judged:
    bound, first = _comp(m.bound, env.at(0))
    if not isinstance(bound, F | Bottom):
        env.at(0).refuse(TypeErrorKind.NOT_RETURNER, f"`to` after {bound!r}")
    returned = bound.value if isinstance(bound, F) else Zero()
    body, rest = _comp(m.body, env.at(3).bind(m.name, returned, m.grade))
    return (Bottom() if isinstance(bound, Bottom) else body), first | rest


def _judge_force(m: Force, env: _Env) -> Judged:
    thunk = _value(m.value, env.at(0))
    if not isinstance(thunk, U):
        env.refuse(TypeErrorKind.NOT_THUNK, f"`force` of {thunk!r}")
    return thunk.comp, thunk.eff


def _judge_lam(m: Lam, env: _Env) -> Judged:
    body, eff = _comp(m.body, env.at(3).bind(m.name, m.type, m.grade))
    return Arrow(m.type, body), eff


def _judge_app(m: App, env: _Env) -> Judged:
    fun, eff = _comp(m.fun, env.at(1))
    arg = _value(m.arg, env.at(0))
    if isinstance(fun, Bottom):
        return fun, eff
    if not isinstance(fun, Arrow):
        env.refuse(TypeErrorKind.NOT_FUNCTION, f"an argument pushed onto {fun!r}")
    env.at(0).fit(arg, fun.arg)
    return fun.res, eff


def _judge_split(m: SplitPair, env: _Env) -> Judged:
    pair = _value(m.value, env.at(0))
    if not isinstance(pair, Prod):
        env.refuse(TypeErrorKind.NOT_PAIR, f"`pm` as a pair of {pair!r}")
    inner = env.at(5).bind(m.left, pair.left, m.left_grade)
    return _comp(m.body, inner.bind(m.right, pair.right, m.right_grade))


def _judge_case(m: Case, env: _Env) -> Judged:
    sum_ = _value(m.value, env.at(0))
    if not isinstance(sum_, Sum):
        env.refuse(TypeErrorKind.NOT_SUM, f"`pm` as a sum of {sum_!r}")
    left, el = _comp(m.left, env.at(3).bind(m.left_name, sum_.left, m.left_grade))
    right, er = _comp(m.right, env.at(6).bind(m.right_name, sum_.right, m.right_grade))
    joined: CType = _widen(left, right)
    env.fit(left, joined)
    env.fit(right, joined)
    return joined, el | er


def _judge_absurd(m: Absurd, env: _Env) -> Judged:
    env.at(0).fit(_value(m.value, env.at(0)), Zero())
    return m.type, PURE


def _judge_both(m: Both, env: _Env) -> Judged:
    left, el = _comp(m.left, env.at(0))
    right, er = _comp(m.right, env.at(1))
    return With(left, right), el | er


def _project(m: First | Second, env: _Env) -> tuple[With | Bottom, Effects]:
    both, eff = _comp(m.comp, env.at(0))
    if not isinstance(both, With | Bottom):
        env.refuse(TypeErrorKind.NOT_WITH, f"a projection of {both!r}")
    return both, eff


def _judge_first(m: First, env: _Env) -> Judged:
    both, eff = _project(m, env)
    return (both if isinstance(both, Bottom) else both.left), eff


def _judge_second(m: Second, env: _Env) -> Judged:
    both, eff = _project(m, env)
    return (both if isinstance(both, Bottom) else both.right), eff


def _judge_rec(m: Rec, env: _Env) -> Judged:
    if "div" not in m.eff:
        env.refuse(TypeErrorKind.REC_WITHOUT_DIV, f"`rec {m.name}` without div")
    inner = env.at(4).bind(m.name, U(m.type, m.eff), m.grade)
    body, eff = _comp(m.body, inner)
    inner.fit(body, m.type)
    if not eff <= m.eff:
        inner.refuse(TypeErrorKind.EFFECT_ESCAPES, f"{sorted(eff - m.eff)} undeclared")
    return m.type, m.eff


def _judge_op(m: Op, env: _Env) -> Judged:
    cap = _value(m.cap, env.at(1))
    ops = env.sig.caps.get(cap.name) if isinstance(cap, Base) else None
    if ops is None:
        env.at(1).refuse(TypeErrorKind.MISMATCH, f"{cap!r} is not a capability")
    if m.op not in ops:
        env.refuse(TypeErrorKind.OP_UNKNOWN, f"no operation {m.op} on {cap!r}")
    want, result = ops[m.op]
    arg = _value(m.arg, env.at(2))
    if arg != want:
        env.at(2).refuse(TypeErrorKind.MISMATCH, f"{arg!r} is not {want!r}")
    return F(result), PURE


def _judge_fail(m: Fail, env: _Env) -> Judged:
    env.at(0).fit(_value(m.payload, env.at(0)), env.sig.fail_payload)
    return Bottom(), frozenset({"fail"})


def _judge_label(m: Label, env: _Env) -> Judged:
    return _comp(m.body, env.at(1))


def _judge_prim(m: Prim, env: _Env) -> Judged:
    constant = env.sig.constants.get(m.name)
    known = isinstance(constant, FirstOrder | Iterating) and len(_params(m.type)) >= constant.arity
    if not (known and env.sig.admits(m)):
        env.refuse(TypeErrorKind.PRIM_INSTANCE, f"no instance {m.name} : {m.type!r}")
    return m.type, m.eff


def _params(t: CType) -> tuple[VType, ...]:
    """The arguments a computation of type `t` pops, in order."""
    return (t.arg, *_params(t.res)) if isinstance(t, Arrow) else ()


_COMPS: dict[type, Callable[[Any, _Env], Judged]] = {
    Return: _judge_return,
    To: _judge_to,
    Force: _judge_force,
    Lam: _judge_lam,
    App: _judge_app,
    SplitPair: _judge_split,
    Case: _judge_case,
    Absurd: _judge_absurd,
    Both: _judge_both,
    First: _judge_first,
    Second: _judge_second,
    Rec: _judge_rec,
    Op: _judge_op,
    Fail: _judge_fail,
    Label: _judge_label,
    Prim: _judge_prim,
}


# One label per loop.


def leads(m: Comp) -> bool:
    """`M` leads with a label: `label l. _`, or a pair `<M1, M2>` with both leading."""
    match m:
        case Label():
            return True
        case Both(left=left, right=right):
            return leads(left) and leads(right)
        case _:
            return False


def _unlabelled(x: object, sig: Signature, path: Path) -> Path | None:
    """The path to the first loop body under `x` that does not lead with a label."""
    if isinstance(x, Rec) and not leads(x.body):
        return (*path, 4)
    if isinstance(x, App | Prim):
        return _spine(x, sig, path)
    return _first_unlabelled(_children(x, path), sig)


def _spine(m: App | Prim, sig: Signature, path: Path) -> Path | None:
    """A spine `App(V1, ... App(Vn, H))`: `H` pops `Vn` first, so the innermost comes first."""
    args: list[tuple[Value, Path]] = []
    head: Comp = m
    while isinstance(head, App):
        args.append((head.arg, (*path, 0)))
        head, path = head.fun, (*path, 1)
    args.reverse()
    if not isinstance(head, Prim):
        return _first_unlabelled(iter([*args, (head, path)]), sig)
    found = _loop_body(head, args, sig, path)
    return found if found is not None else _first_unlabelled(iter(args), sig)


def _loop_body(
    head: Prim, args: list[tuple[Value, Path]], sig: Signature, path: Path
) -> Path | None:
    """Where a constant's spine fails the label rule: an iterating constant given fewer than
    its arity, or a thunk argument that is not a literal leading with a label."""
    constant = sig.constants.get(head.name)
    if isinstance(constant, Iterating) and len(args) < constant.arity:
        return path
    for (arg, where), param in zip(args, _params(head.type), strict=False):
        if isinstance(param, U) and not (isinstance(arg, Thunk) and leads(arg.body)):
            return where
    return None


def _first_unlabelled(nodes: Iterator[tuple[object, Path]], sig: Signature) -> Path | None:
    for node, path in nodes:
        found = _unlabelled(node, sig, path)
        if found is not None:
            return found
    return None


def _children(x: object, path: Path) -> Iterator[tuple[object, Path]]:
    if isinstance(x, tuple):
        items: tuple[object, ...] = x  # pyright: ignore[reportUnknownVariableType] -- a node's tuple
    elif is_dataclass(x):
        items = tuple(getattr(x, f.name) for f in fields(x))
    else:
        items = ()
    return ((item, (*path, i)) for i, item in enumerate(items))
