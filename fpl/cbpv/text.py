"""Levy's notation for the IR, for review and for failure messages.

Promised: `print` is injective on structure (law print-injective): every field that enters a
node's equality is printed, every compound form is bracketed, one binder per line. Not
printed: `Prim.at` and `Thunk.origin`, which do not enter equality. Not promised: a parser;
the text is for reading.

Each class has one rule, reached through a table keyed by class; each rule matches its node
with a keyword pattern naming every compared field, so a field added to `syntax` and not
printed is a gap one can see.
"""

from collections.abc import Callable
from typing import Any, assert_never

from fpl.cbpv.syntax import (
    Absurd,
    App,
    Arrow,
    Base,
    Both,
    Case,
    Const,
    Dyn,
    Effects,
    F,
    Fail,
    First,
    Force,
    Inl,
    Inr,
    Label,
    LabelKey,
    Lam,
    Node,
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
    U,
    Unit,
    Var,
    With,
    Zero,
)


def print(node: Node) -> str:
    """The node in Levy's notation."""
    return _RULES[type(node)](node)


def effects(eff: Effects) -> str:
    """An effect set, sorted: `{div, fail}`."""
    return "{" + ", ".join(sorted(eff)) + "}"


def _group(node: Node) -> str:
    return f"({print(node)})"


def _base(t: Base) -> str:
    match t:
        case Base(name=n):
            return n
        case _:
            assert_never(t)


def _prod(t: Prod) -> str:
    match t:
        case Prod(left=a, right=b):
            return f"({print(a)} * {print(b)})"
        case _:
            assert_never(t)


def _sum(t: Sum) -> str:
    match t:
        case Sum(left=a, right=b):
            return f"({print(a)} + {print(b)})"
        case _:
            assert_never(t)


def _u(t: U) -> str:
    match t:
        case U(comp=b, eff=e):
            return f"(U{effects(e)} {print(b)})"
        case _:
            assert_never(t)


def _f(t: F) -> str:
    match t:
        case F(value=a):
            return f"(F {print(a)})"
        case _:
            assert_never(t)


def _arrow(t: Arrow) -> str:
    match t:
        case Arrow(arg=a, res=b):
            return f"({print(a)} → {print(b)})"
        case _:
            assert_never(t)


def _with(t: With) -> str:
    match t:
        case With(left=a, right=b):
            return f"({print(a)} & {print(b)})"
        case _:
            assert_never(t)


def _var(v: Var) -> str:
    match v:
        case Var(name=x):
            return x
        case _:
            assert_never(v)


def _const(v: Const) -> str:
    match v:
        case Const(value=c, type=a):
            return f"({c!r} : {print(a)})"
        case _:
            assert_never(v)


def _pair(v: Pair) -> str:
    match v:
        case Pair(left=a, right=b):
            return f"({print(a)}, {print(b)})"
        case _:
            assert_never(v)


def _inl(v: Inl) -> str:
    match v:
        case Inl(value=a, right=t):
            return f"(inl {print(a)} + {print(t)})"
        case _:
            assert_never(v)


def _inr(v: Inr) -> str:
    match v:
        case Inr(value=a, left=t):
            return f"(inr {print(t)} + {print(a)})"
        case _:
            assert_never(v)


def _thunk(v: Thunk) -> str:
    match v:
        case Thunk(body=m):
            return f"(thunk {_group(m)})"
        case _:
            assert_never(v)


def _return(m: Return) -> str:
    match m:
        case Return(value=v):
            return f"return {print(v)}"
        case _:
            assert_never(m)


def _to(m: To) -> str:
    match m:
        case To(bound=b, name=x, grade=q, body=n):
            return f"{_group(b)} to {x} :{q}.\n{_group(n)}"
        case _:
            assert_never(m)


def _force(m: Force) -> str:
    match m:
        case Force(value=v):
            return f"force {print(v)}"
        case _:
            assert_never(m)


def _lam(m: Lam) -> str:
    match m:
        case Lam(name=x, type=a, grade=q, body=n):
            return f"λ{x} :{q} {print(a)}.\n{_group(n)}"
        case _:
            assert_never(m)


def _app(m: App) -> str:
    match m:
        case App(arg=v, fun=n):
            return f"{print(v)} ` {_group(n)}"
        case _:
            assert_never(m)


def _split(m: SplitPair) -> str:
    match m:
        case SplitPair(value=v, left=x, left_grade=q, right=y, right_grade=r, body=n):
            return f"pm {print(v)} as ({x} :{q}, {y} :{r}).\n{_group(n)}"
        case _:
            assert_never(m)


def _case(m: Case) -> str:
    match m:
        case Case(value=v, left_name=x, left_grade=q, left=a, right_name=y, right_grade=r, right=b):
            head = f"pm {print(v)} as {{inl {x} :{q}.\n{_group(a)}"
            return f"{head}\n| inr {y} :{r}.\n{_group(b)}}}"
        case _:
            assert_never(m)


def _absurd(m: Absurd) -> str:
    match m:
        case Absurd(value=v, type=b):
            return f"absurd {print(v)} : {print(b)}"
        case _:
            assert_never(m)


def _both(m: Both) -> str:
    match m:
        case Both(left=a, right=b):
            return f"⟨{_group(a)}, {_group(b)}⟩"
        case _:
            assert_never(m)


def _first(m: First) -> str:
    match m:
        case First(comp=n):
            return f"fst {_group(n)}"
        case _:
            assert_never(m)


def _second(m: Second) -> str:
    match m:
        case Second(comp=n):
            return f"snd {_group(n)}"
        case _:
            assert_never(m)


def _rec(m: Rec) -> str:
    match m:
        case Rec(name=x, grade=q, type=b, eff=e, body=n):
            return f"rec {x} :{q} U{effects(e)} {print(b)}.\n{_group(n)}"
        case _:
            assert_never(m)


def _op(m: Op) -> str:
    match m:
        case Op(op=o, cap=v, arg=w):
            return f"op {o} {print(v)} {print(w)}"
        case _:
            assert_never(m)


def _fail(m: Fail) -> str:
    match m:
        case Fail(payload=v):
            return f"fail {print(v)}"
        case _:
            assert_never(m)


def _key(k: LabelKey) -> str:
    match k:
        case LabelKey(word=w, ordinal=i):
            return f"&{w!r}#{i}"
        case _:
            assert_never(k)


def _label(m: Label) -> str:
    match m:
        case Label(label=k, body=n):
            return f"label {print(k)}.\n{_group(n)}"
        case _:
            assert_never(m)


def _prim(m: Prim) -> str:
    match m:
        case Prim(name=p, type=b, eff=e):
            return f"prim {p} : {print(b)} ! {effects(e)}"
        case _:
            assert_never(m)


def _program(p: Program) -> str:
    match p:
        case Program(defs=defs, runs=runs):
            lines = [f"{x} = {print(v)}" for x, v in defs]
            return "\n".join([*lines, *(f"run {_group(m)}" for m in runs)])
        case _:
            assert_never(p)


_RULES: dict[type, Callable[[Any], str]] = {
    Base: _base,
    Dyn: lambda _: "Dyn",
    One: lambda _: "1",
    Zero: lambda _: "0",
    Prod: _prod,
    Sum: _sum,
    U: _u,
    F: _f,
    Arrow: _arrow,
    Top: lambda _: "Top",
    With: _with,
    Var: _var,
    Const: _const,
    Unit: lambda _: "()",
    Pair: _pair,
    Inl: _inl,
    Inr: _inr,
    Thunk: _thunk,
    Return: _return,
    To: _to,
    Force: _force,
    Lam: _lam,
    App: _app,
    SplitPair: _split,
    Case: _case,
    Absurd: _absurd,
    Both: _both,
    First: _first,
    Second: _second,
    Rec: _rec,
    Op: _op,
    Fail: _fail,
    LabelKey: _key,
    Label: _label,
    Prim: _prim,
    Program: _program,
}
