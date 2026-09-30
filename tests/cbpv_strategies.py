"""Hypothesis strategies for the CBPV IR: structural shapes (not typed); the test signature
Σ_test with arguments for its constants; programs well typed by construction; and the catalogue
of ill-typed ones, one mutation per `TypeErrorKind`."""

from collections.abc import Callable, Hashable
from dataclasses import dataclass, replace
from functools import cache
from typing import Any

from hypothesis import strategies as st

from fpl.cbpv.check import TypeErrorKind
from fpl.cbpv.sig import Call, Done, FirstOrder, Iterating, Panic, Signature, Step
from fpl.cbpv.syntax import (
    KNOWN,
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
    LabelKey,
    Lam,
    Node,
    One,
    Op,
    Pair,
    Position,
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
    Value,
    Var,
    VType,
    With,
    Zero,
)

DEPTH = 3
names = st.sampled_from(("x", "y", "z"))
grades: st.SearchStrategy[Grade] = st.sampled_from((0, 1, "ω"))
effect_sets: st.SearchStrategy[Effects] = st.frozensets(st.sampled_from(("div", "fail")))
positions = st.none() | st.builds(Position, st.integers(1, 99), st.integers(1, 99))
keys = st.builds(LabelKey, st.sampled_from(("w", "line 1")), st.integers(0, 3))
# Values of distinct Python types print distinctly (repr), so the printer can tell them apart.
atoms = st.integers(-3, 3) | st.sampled_from(("a", "b"))
LEAF_TYPES: tuple[VType, ...] = (Base("Int"), Base("Log"), Dyn(), One(), Zero())


@cache
def vtypes(depth: int) -> st.SearchStrategy[VType]:
    """Value types up to `depth` constructors deep."""
    leaves = st.sampled_from(LEAF_TYPES)
    if depth == 0:
        return leaves
    v, c = vtypes(depth - 1), ctypes(depth - 1)
    return leaves | st.builds(Prod, v, v) | st.builds(Sum, v, v) | st.builds(U, c, effect_sets)


@cache
def ctypes(depth: int) -> st.SearchStrategy[CType]:
    """Computation types up to `depth` constructors deep."""
    if depth == 0:
        return st.just(Top()) | st.builds(F, vtypes(0))
    v, c = vtypes(depth - 1), ctypes(depth - 1)
    return st.just(Top()) | st.builds(F, v) | st.builds(Arrow, v, c) | st.builds(With, c, c)


@cache
def values(depth: int) -> st.SearchStrategy[Value]:
    """Values up to `depth` constructors deep, thunks with their origins drawn."""
    leaves = st.builds(Var, names) | st.builds(Const, atoms, vtypes(0)) | st.just(Unit())
    if depth == 0:
        return leaves
    v, t, m = values(depth - 1), vtypes(depth - 1), comps(depth - 1)
    origins = st.none() | st.integers(0, 9)
    return (
        leaves
        | st.builds(Pair, v, v)
        | st.builds(Inl, v, t)
        | st.builds(Inr, v, t)
        | st.builds(Thunk, m, origins)
    )


@cache
def comps(depth: int) -> st.SearchStrategy[Comp]:
    """Computations up to `depth` constructors deep, constants with their positions drawn."""
    v0, c0 = values(0), ctypes(0)
    leaves = (
        st.builds(Return, v0)
        | st.builds(Force, v0)
        | st.builds(Fail, v0)
        | st.builds(Op, names, v0, v0)
        | st.builds(Absurd, v0, c0)
        | st.builds(Prim, names, c0, effect_sets, positions)
    )
    if depth == 0:
        return leaves
    v, m, t, c = values(depth - 1), comps(depth - 1), vtypes(depth - 1), ctypes(depth - 1)
    return (
        leaves
        | st.builds(To, m, names, grades, m)
        | st.builds(Lam, names, t, grades, m)
        | st.builds(App, v, m)
        | st.builds(SplitPair, v, names, grades, names, grades, m)
        | st.builds(Case, v, names, grades, m, names, grades, m)
        | st.builds(Both, m, m)
        | st.builds(First, m)
        | st.builds(Second, m)
        | st.builds(Rec, names, grades, c, effect_sets, m)
        | st.builds(Label, keys, m)
    )


def programs_shaped() -> st.SearchStrategy[Program]:
    """Programs of shaped definitions and runs, each name defined once."""
    defs = st.lists(st.tuples(names, values(1)), max_size=3, unique_by=lambda d: d[0])
    return st.builds(Program, defs.map(tuple), st.lists(comps(1), max_size=2).map(tuple))


def shapes() -> st.SearchStrategy[Node]:
    """Structural IR nodes of every class, not typed; positions and origins drawn."""
    return st.one_of(
        vtypes(DEPTH), ctypes(DEPTH), values(DEPTH), comps(DEPTH), keys, programs_shaped()
    )


# Σ_test: `Int` with `add`, `sub`, a `div` that panics on zero, the iterating `times_k`, and
# the capability type `Log` with `emit : Int → Int`.

INT, LOG = Base("Int"), Base("Log")
PURE: Effects = frozenset()
HANDLE = "log"  # the one `Log` value; at a `Dyn` input it is outside every constant's domain
BINARY = Arrow(INT, Arrow(INT, F(INT)))
BODY = Arrow(INT, F(INT))
SCHEMES: dict[str, CType] = {
    "add": BINARY,
    "sub": BINARY,
    "div": BINARY,
    "times_k": Arrow(INT, Arrow(U(BODY, PURE), F(INT))),
}


def arithmetic(op: Callable[[int, int], int | None]) -> FirstOrder:
    """A binary constant on `Int`: a `Panic` for a non-integer argument or when `op` refuses."""

    def apply(args: tuple[Hashable, ...], _at: Position | None) -> Const | Panic:
        a, b = args
        if not (type(a) is int and type(b) is int):
            return Panic("arithmetic on a non-number")
        result = op(a, b)
        return Panic("division by zero") if result is None else Const(result, INT)

    return FirstOrder(2, apply)


def _input(got: VType, scheme: VType) -> bool:
    thunks = isinstance(got, U) and isinstance(scheme, U) and got.comp == scheme.comp
    return got == scheme or thunks or (got == Dyn() and isinstance(scheme, Base))


def _instance(got: CType, scheme: CType) -> bool:
    if isinstance(got, Arrow) and isinstance(scheme, Arrow):
        return _input(got.arg, scheme.arg) and _instance(got.res, scheme.res)
    return got == scheme


def _latent(t: CType) -> Effects:
    """The effects of the thunks a constant of type `t` receives: forcing them is its effect."""
    if not isinstance(t, Arrow):
        return PURE
    return (t.arg.eff if isinstance(t.arg, U) else PURE) | _latent(t.res)


def admits(p: Prim) -> bool:
    """`p` is its scheme with `Dyn` at any base input and any latent effect on its thunk."""
    scheme = SCHEMES.get(p.name)
    return scheme is not None and _instance(p.type, scheme) and p.eff == _latent(p.type)


def times_start(args: tuple[Any, ...], _at: Position | None) -> Step | Panic:
    """`times_k k f` runs `f` k times from 0, each run on the last one's result: f^k(0)."""
    count, body = args
    k = count.value if isinstance(count, Const) else None
    if type(k) is not int:
        return Panic("times_k takes a count")
    return times_resume((body, k), Const(0, INT))


def times_resume(state: Any, result: Any) -> Step | Panic:
    """With `n` runs left, run the body on `result`, or return it when none is left."""
    body, n = state
    return Done(result) if n <= 0 else Call(body, (result,), (body, n - 1))


SIGMA_TEST = Signature(
    bases=frozenset({"Int", "Log"}),
    constants={
        "add": arithmetic(lambda a, b: a + b),
        "sub": arithmetic(lambda a, b: a - b),
        "div": arithmetic(lambda a, b: a // b if b else None),
        "times_k": Iterating(2, times_start, times_resume),
    },
    admits=admits,
    caps={"Log": {"emit": (INT, INT)}},
    fail_payload=INT,
)
FIRST_ORDER = ("add", "sub", "div")
PANICS = frozenset({"arithmetic on a non-number", "division by zero", "times_k takes a count"})


def base_value(t: VType) -> st.SearchStrategy[Hashable]:
    """A Python value at `t`: an integer at `Int` (zero included), any base value at `Dyn`."""
    ints = st.integers(-4, 4)
    return ints | st.just(HANDLE) if t == Dyn() else ints


@st.composite
def constant_args(draw: st.DrawFn) -> tuple[Prim, tuple[Hashable, ...]]:
    """A first-order constant of Σ_test at a drawn instance, and arguments at its inputs."""
    inputs = draw(st.tuples(*[st.sampled_from((INT, Dyn()))] * 2))
    prim = Prim(
        draw(st.sampled_from(FIRST_ORDER)), Arrow(inputs[0], Arrow(inputs[1], F(INT))), PURE, None
    )
    return prim, tuple(draw(base_value(t)) for t in inputs)


# Programs well typed by construction.

SIZE = 3


@dataclass(frozen=True)
class Scope:
    """What a term may mention: the signature, the usable variables and their types, the next
    fresh index, the depth it may still grow, the effects it may have, whether `Dyn` is drawn."""

    sig: Signature
    vars: tuple[tuple[str, VType], ...]
    fresh: int
    depth: int
    eff: Effects
    dyn: bool

    def deeper(self) -> "Scope":
        return replace(self, depth=max(self.depth - 1, 0))

    def bind(self, grade: Grade, vtype: VType) -> tuple[str, "Scope"]:
        """A fresh name, usable below unless its grade is 0."""
        name = f"x{self.fresh}"
        usable = self.vars if grade == 0 else (*self.vars, (name, vtype))
        return name, replace(self, vars=usable, fresh=self.fresh + 1)


@cache
def vgoals(depth: int) -> st.SearchStrategy[VType]:
    """Inhabited value types: `Int`, `Log`, `1`, products, sums, thunks."""
    leaves: st.SearchStrategy[VType] = st.sampled_from((INT, LOG, One()))
    if depth == 0:
        return leaves
    v = vgoals(depth - 1)
    return (
        leaves
        | st.builds(Prod, v, v)
        | st.builds(Sum, v, v)
        | st.builds(U, cgoals(depth - 1), effect_sets)
    )


@cache
def params(depth: int) -> st.SearchStrategy[VType]:
    """Argument types, uninhabited ones included (`0`, a thunk of `Top`)."""
    return vgoals(depth) | st.just(Zero()) | st.builds(U, st.just(Top()), effect_sets)


@cache
def cgoals(depth: int) -> st.SearchStrategy[CType]:
    """Inhabited computation types: `F A`, arrows, and products of computations."""
    returners: st.SearchStrategy[CType] = st.builds(F, vgoals(depth))
    if depth == 0:
        return returners
    c = cgoals(depth - 1)
    return returners | st.builds(Arrow, params(depth - 1), c) | st.builds(With, c, c)


def value_of(d: st.DrawFn, t: VType, s: Scope) -> Value:
    """A value of type `t`: one of the variables of that type, or its introduction form."""
    usable: list[Value | None] = [Var(name) for name, vt in s.vars if vt == t]
    return d(st.sampled_from(usable if t == Zero() else [*usable, None])) or _intro_value(d, t, s)


def _intro_value(d: st.DrawFn, t: VType, s: Scope) -> Value:
    match t:
        case Base(name="Log"):
            return Const(HANDLE, LOG)
        case Base():
            return Const(d(st.integers(-4, 4)), t)
        case Prod(left=a, right=b):
            return Pair(value_of(d, a, s), value_of(d, b, s))
        case Sum(left=a, right=b):
            return Inl(value_of(d, a, s), b) if d(st.booleans()) else Inr(value_of(d, b, s), a)
        case U(comp=b, eff=eff):
            return Thunk(
                comp_of(d, b, replace(s, eff=eff).deeper()), d(st.none() | st.integers(0, 9))
            )
        case One():
            return Unit()
        case _:
            raise AssertionError(t)


def comp_of(d: st.DrawFn, goal: CType, s: Scope) -> Comp:
    """A computation of type `goal` whose effects are within `s.eff`."""
    forms = [_intro] if s.depth == 0 else [f for f, ok in _forms(goal, s) if ok]
    return d(st.sampled_from(forms))(d, goal, s)


type Former = Callable[[st.DrawFn, CType, Scope], Comp]


def _forms(goal: CType, s: Scope) -> list[tuple[Former, bool]]:
    returns_int = goal == F(INT)
    return [
        (_intro, True),
        (_to, True),
        (_app, True),
        (_force, True),
        (_split, True),
        (_case, True),
        (_label, True),
        (_project, True),
        (_rec, "div" in s.eff),
        (_fail, "fail" in s.eff),
        (_arith, returns_int),
        (_op, returns_int),
        (_times, returns_int),
    ]


def _intro(d: st.DrawFn, goal: CType, s: Scope) -> Comp:
    match goal:
        case F(value=a):
            return Return(value_of(d, a, s))
        case Arrow(arg=a, res=b):
            grade = d(grades)
            name, inner = s.bind(grade, a)
            # A λ over 0 is never applied; its body eliminates the variable.
            body = (
                Absurd(Var(name), b)
                if a == Zero() and grade != 0
                else comp_of(d, b, inner.deeper())
            )
            return Lam(name, a, grade, body)
        case With(left=b, right=c):
            return Both(comp_of(d, b, s.deeper()), comp_of(d, c, s.deeper()))
        case _:
            raise AssertionError(goal)


def _to(d: st.DrawFn, goal: CType, s: Scope) -> Comp:
    a, grade = d(vgoals(1)), d(grades)
    name, inner = s.bind(grade, a)
    # A bound without `fail` returns, so its variable keeps the type drawn for it.
    bound = comp_of(d, F(a), replace(s, eff=s.eff - {"fail"}).deeper())
    return To(bound, name, grade, comp_of(d, goal, inner.deeper()))


def _app(d: st.DrawFn, goal: CType, s: Scope) -> Comp:
    a = d(vgoals(1))
    return App(value_of(d, a, s.deeper()), comp_of(d, Arrow(a, goal), s.deeper()))


def _force(d: st.DrawFn, goal: CType, s: Scope) -> Comp:
    eff = d(st.sampled_from(sorted(_subsets(s.eff), key=sorted)))
    return Force(value_of(d, U(goal, eff), s.deeper()))


def _split(d: st.DrawFn, goal: CType, s: Scope) -> Comp:
    a, b, ga, gb = d(vgoals(1)), d(vgoals(1)), d(grades), d(grades)
    x, inner = s.bind(ga, a)
    y, inner = inner.bind(gb, b)
    return SplitPair(
        value_of(d, Prod(a, b), s.deeper()), x, ga, y, gb, comp_of(d, goal, inner.deeper())
    )


def _case(d: st.DrawFn, goal: CType, s: Scope) -> Comp:
    a, b, ga, gb = d(vgoals(1)), d(vgoals(1)), d(grades), d(grades)
    x, left = s.bind(ga, a)
    y, right = s.bind(gb, b)
    branch = comp_of(d, goal, left.deeper()), comp_of(d, goal, right.deeper())
    return Case(value_of(d, Sum(a, b), s.deeper()), x, ga, branch[0], y, gb, branch[1])


def _label(d: st.DrawFn, goal: CType, s: Scope) -> Comp:
    return Label(d(keys), comp_of(d, goal, s.deeper()))


def _project(d: st.DrawFn, goal: CType, s: Scope) -> Comp:
    other = d(cgoals(0))
    if d(st.booleans()):
        return First(comp_of(d, With(goal, other), s.deeper()))
    return Second(comp_of(d, With(other, goal), s.deeper()))


def _rec(d: st.DrawFn, goal: CType, s: Scope) -> Comp:
    """`rec x : U_ε B. label l. M` whose body does not call itself: Σ_test has no test on
    `Int`, so no decreasing guard can be written (decision rec-guard)."""
    eff = d(st.sampled_from(sorted((e for e in _subsets(s.eff) if "div" in e), key=sorted)))
    grade = d(grades)
    name, inner = s.bind(0, U(goal, eff))
    body = Label(d(keys), comp_of(d, goal, replace(inner, eff=eff).deeper()))
    return Rec(name, grade, goal, eff, body)


def _fail(d: st.DrawFn, _goal: CType, s: Scope) -> Comp:
    return Fail(value_of(d, s.sig.fail_payload, s.deeper()))


def _input_value(d: st.DrawFn, s: Scope) -> tuple[VType, Value]:
    """A constant's `Int` input: at `Dyn`, when drawn, carrying any base value."""
    if s.dyn and d(st.booleans()):
        return Dyn(), Const(d(base_value(Dyn())), Dyn())
    return INT, value_of(d, INT, s.deeper())


def _arith(d: st.DrawFn, _goal: CType, s: Scope) -> Comp:
    (a, v), (b, w) = _input_value(d, s), _input_value(d, s)
    prim = Prim(d(st.sampled_from(FIRST_ORDER)), Arrow(a, Arrow(b, F(INT))), PURE, d(positions))
    return App(w, App(v, prim))


def _op(d: st.DrawFn, _goal: CType, s: Scope) -> Comp:
    cap, (op, (arg, _)) = d(
        st.sampled_from([(c, o) for c, ops in s.sig.caps.items() for o in ops.items()])
    )
    return Op(op, value_of(d, Base(cap), s.deeper()), value_of(d, arg, s.deeper()))


def _times(d: st.DrawFn, _goal: CType, s: Scope) -> Comp:
    """`App(thunk (label l. λn. M), App(k, times_k))`: the loop body leads with a label."""
    eff = d(st.sampled_from(sorted(_subsets(s.eff), key=sorted)))
    k, count = _input_value(d, s)
    grade = d(grades)
    name, inner = s.bind(grade, INT)
    loop = Lam(name, INT, grade, comp_of(d, F(INT), replace(inner, eff=eff).deeper()))
    prim = Prim("times_k", Arrow(k, Arrow(U(BODY, eff), F(INT))), eff, d(positions))
    return App(Thunk(Label(d(keys), loop)), App(count, prim))


SUBSETS: tuple[Effects, ...] = (PURE, frozenset({"div"}), frozenset({"fail"}), KNOWN)


def _subsets(eff: Effects) -> list[Effects]:
    return [e for e in SUBSETS if e <= eff]


@st.composite
def programs(d: st.DrawFn, sig: Signature, *, dyn: bool = True) -> Program:
    """A program `check(program, sig, loops=True)` accepts, over Σ_test's constants: up to two
    definitions, each over those before it, and one or two runs of type `F A`."""
    s = Scope(sig, (), 0, SIZE, PURE, dyn)
    defs: list[tuple[str, Value]] = []
    for i in range(d(st.integers(0, 2))):
        t = d(vgoals(2))
        defs.append((f"d{i}", value_of(d, t, s)))
        s = replace(s, vars=(*s.vars, (f"d{i}", t)))
    runs = [
        comp_of(d, F(d(vgoals(2))), replace(s, eff=d(st.sampled_from(_subsets(KNOWN)))))
        for _ in range(d(st.integers(1, 2)))
    ]
    return Program(tuple(defs), tuple(runs))


# The catalogue: one ill-typed run per kind (grade 0 through every binder form), each
# appended to a drawn well-typed program, so the checker meets it after valid runs.

ONE = Const(1, INT)
KEY = LabelKey("w", 0)
DIV: Effects = frozenset({"div"})
LOOP = Thunk(Label(KEY, Lam("n", INT, 1, Return(Var("n")))))
TIMES = Prim("times_k", SCHEMES["times_k"], PURE, None)


def rec(grade: Grade, eff: Effects, body: Comp) -> Rec:
    """`rec f : U_eff (F Int). body`."""
    return Rec("f", grade, F(INT), eff, body)


def labelled(m: Comp) -> Comp:
    return Label(KEY, m)


K = TypeErrorKind
CATALOGUE: tuple[tuple[TypeErrorKind, Comp], ...] = (
    (K.UNBOUND, Return(Var("nowhere"))),
    (K.MISMATCH, App(ONE, Lam("x", LOG, 1, Return(Var("x"))))),
    (K.NOT_THUNK, Force(ONE)),
    (K.NOT_FUNCTION, App(ONE, Return(ONE))),
    (K.NOT_RETURNER, To(Lam("x", INT, 1, Return(Var("x"))), "y", 1, Return(ONE))),
    (K.NOT_PAIR, SplitPair(ONE, "x", 1, "y", 1, Return(ONE))),
    (K.NOT_SUM, Case(ONE, "x", 1, Return(ONE), "y", 1, Return(ONE))),
    (K.NOT_WITH, First(Return(ONE))),
    (K.EFFECT_ESCAPES, rec(1, DIV, labelled(Fail(ONE)))),
    (K.REC_WITHOUT_DIV, rec(1, frozenset({"fail"}), labelled(Return(ONE)))),
    (K.GRADE_ZERO_USED, App(ONE, Lam("x", INT, 0, Return(Var("x"))))),
    (K.GRADE_ZERO_USED, To(Return(ONE), "x", 0, Return(Var("x")))),
    (K.GRADE_ZERO_USED, SplitPair(Pair(ONE, ONE), "x", 0, "y", 1, Return(Var("x")))),
    (K.GRADE_ZERO_USED, SplitPair(Pair(ONE, ONE), "x", 1, "y", 0, Return(Var("y")))),
    (K.GRADE_ZERO_USED, Case(Inl(ONE, INT), "x", 0, Return(Var("x")), "y", 1, Return(ONE))),
    (K.GRADE_ZERO_USED, Case(Inl(ONE, INT), "x", 1, Return(ONE), "y", 0, Return(Var("y")))),
    (K.GRADE_ZERO_USED, rec(0, DIV, labelled(Force(Var("f"))))),
    (K.PRIM_INSTANCE, App(ONE, App(ONE, Prim("add", BINARY, frozenset({"fail"}), None)))),
    (K.OP_UNKNOWN, Op("shout", Const(HANDLE, LOG), ONE)),
    (K.LOOP_UNLABELLED, rec(1, DIV, Return(ONE))),
    (K.LOOP_UNLABELLED, App(Thunk(Lam("n", INT, 1, Return(Var("n")))), App(ONE, TIMES))),
)


def invalid(sig: Signature) -> st.SearchStrategy[tuple[TypeErrorKind, Program]]:
    """A drawn program with one catalogue run appended, tagged with the kind it must get."""

    def mutate(
        program: Program, entry: tuple[TypeErrorKind, Comp]
    ) -> tuple[TypeErrorKind, Program]:
        return entry[0], Program(program.defs, (*program.runs, entry[1]))

    return st.builds(mutate, programs(sig), st.sampled_from(CATALOGUE))
