"""The checker: accepts what `programs()` builds, refuses each catalogue mutation by kind."""

import pytest
from cbpv_strategies import (
    BINARY,
    BODY,
    CATALOGUE,
    DIV,
    HANDLE,
    INT,
    LOG,
    LOOP,
    ONE,
    SIGMA_TEST,
    TIMES,
    invalid,
    labelled,
    programs,
    rec,
)
from hypothesis import given, seed
from hypothesis import strategies as st
from test_cbpv_syntax import parts

from fpl.cbpv.check import Bottom, TypeError_, TypeErrorKind, check, fits
from fpl.cbpv.syntax import (
    Absurd,
    App,
    Arrow,
    Base,
    Both,
    Case,
    Comp,
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

K = TypeErrorKind
PURE: Effects = frozenset()
FAILS: Effects = frozenset({"fail"})


def run(m: Comp, *, loops: bool = True) -> TypeError_ | None:
    return check(Program((), (m,)), SIGMA_TEST, loops=loops)


@given(st.booleans().flatmap(lambda dyn: programs(SIGMA_TEST, dyn=dyn)))
def test_check_accepts_generated(program: Program) -> None:
    """[law: check-accepts-generated] The checker with `loops=True` accepts every program
    `programs(Σ_test)` draws, with and without `Dyn`."""
    assert check(program, SIGMA_TEST, loops=True) is None


SYNTAX = {
    Var, Const, Unit, Pair, Inl, Inr, Thunk,
    Return, To, Force, Lam, App, SplitPair, Case, Absurd, Both, First, Second, Rec, Op, Fail,
    Label, Prim, LabelKey, Program,
    Base, Dyn, One, Zero, Prod, Sum, U, F, Arrow, Top, With,
}  # fmt: skip


SEEDS = range(20260930, 20260938)


def test_every_class_drawn() -> None:
    """Across a fixed seed set, `programs(Σ_test)` draws every syntax class, and `Dyn` only when
    asked for."""
    seen: set[type] = set()

    @given(programs(SIGMA_TEST), programs(SIGMA_TEST, dyn=False))
    def draw(with_dyn: Program, without: Program) -> None:
        seen.update(type(part) for part in parts(with_dyn))
        assert not any(isinstance(part, Dyn) for part in parts(without))

    for n in SEEDS:
        seed(n)(draw)()
    assert SYNTAX - seen == set()


@given(invalid(SIGMA_TEST))
def test_check_kind_exact(case: tuple[TypeErrorKind, Program]) -> None:
    """[law: check-kind-exact] Each catalogue mutation `invalid(Σ_test)` draws makes the checker
    return a `TypeError_` of exactly that mutation's kind."""
    kind, program = case
    error = check(program, SIGMA_TEST, loops=True)
    assert error is not None
    assert error.kind == kind
    assert error.where[:2] == (1, len(program.runs) - 1)
    assert error.detail


def test_catalogue_has_every_kind() -> None:
    assert {kind for kind, _ in CATALOGUE} == set(TypeErrorKind)


BOTTOM = Thunk(Fail(ONE))
REFUSED: dict[str, tuple[Comp, TypeErrorKind]] = {
    "literal off base": (Return(Const(1, One())), K.MISMATCH),
    "run not returner": (Lam("x", INT, 1, Return(ONE)), K.NOT_RETURNER),
    "absurd of int": (Absurd(ONE, F(INT)), K.MISMATCH),
    "op on int": (Op("emit", ONE, ONE), K.MISMATCH),
    "op on dyn arg": (Op("emit", Const(HANDLE, LOG), Const(1, Dyn())), K.MISMATCH),
    "fail payload": (Fail(Unit()), K.MISMATCH),
    "rec body type": (rec(1, DIV, labelled(Return(Unit()))), K.MISMATCH),
    "second of returner": (Second(Return(ONE)), K.NOT_WITH),
    "case branches": (Case(Inl(ONE, INT), "x", 1, Return(ONE), "y", 1, Return(Unit())), K.MISMATCH),
    "unknown constant": (Prim("nothing", F(INT), PURE, None), K.PRIM_INSTANCE),
    "too few arrows": (Prim("add", F(INT), PURE, None), K.PRIM_INSTANCE),
    "base name": (App(Const(HANDLE, LOG), Lam("x", INT, 1, Return(ONE))), K.MISMATCH),
    "thunk effect": (App(BOTTOM, Lam("t", U(F(INT), PURE), 1, Return(ONE))), K.EFFECT_ESCAPES),
    "undersaturated loop": (
        App(LOOP, App(LOOP, Lam("t", U(BODY, PURE), 1, App(ONE, TIMES)))),
        K.LOOP_UNLABELLED,
    ),
    "loop body a variable": (
        App(LOOP, Lam("t", U(BODY, PURE), 1, App(Var("t"), App(ONE, TIMES)))),
        K.LOOP_UNLABELLED,
    ),
    "half unlabelled": (
        First(Rec("f", 1, With(F(INT), F(INT)), DIV, Both(labelled(Return(ONE)), Return(ONE)))),
        K.LOOP_UNLABELLED,
    ),
}


@pytest.mark.parametrize(("m", "kind"), REFUSED.values(), ids=REFUSED.keys())
def test_refused(m: Comp, kind: TypeErrorKind) -> None:
    error = run(m)
    assert error is not None
    assert error.kind == kind


ACCEPTED: dict[str, Comp] = {
    "to after fail": To(Fail(ONE), "x", 1, Return(Var("x"))),
    "pushed onto fail": App(ONE, Fail(ONE)),
    "first of fail": First(Fail(ONE)),
    "second of both": Second(Both(Return(Unit()), Return(ONE))),
    "labelled pair": First(
        Rec("f", 1, With(F(INT), F(INT)), DIV, Both(labelled(Return(ONE)), labelled(Return(ONE))))
    ),
    "loop": App(LOOP, App(Const(HANDLE, Dyn()), TIMES)),
    "case widens": Case(
        Inr(ONE, INT),
        "x",
        1,
        Return(Pair(Thunk(Return(ONE)), Unit())),
        "y",
        1,
        Return(Pair(BOTTOM, Unit())),
    ),
    "case after fail": Case(Inl(ONE, INT), "x", 1, Fail(ONE), "y", 1, Return(ONE)),
    "pair split": SplitPair(Pair(ONE, Unit()), "x", 1, "y", 1, Return(Var("x"))),
    "op": Op("emit", Const(HANDLE, LOG), ONE),
    "arith": App(ONE, App(ONE, Prim("div", BINARY, PURE, None))),
    "absurd under lambda": Return(Thunk(Lam("z", Zero(), 1, Absurd(Var("z"), Top())))),
    "arrow argument": App(
        Thunk(Lam("x", INT, 1, Return(Var("x")))),
        Lam("g", U(Arrow(INT, F(INT)), FAILS), 1, Return(ONE)),
    ),
}


@pytest.mark.parametrize("m", ACCEPTED.values(), ids=ACCEPTED.keys())
def test_accepted(m: Comp) -> None:
    assert run(m) is None


def test_loops_off_ignores_labels() -> None:
    assert run(rec(1, DIV, Return(ONE)), loops=False) is None


def test_where_is_the_field_path() -> None:
    program = Program((("d", Pair(ONE, Var("nowhere"))),), ())
    assert check(program, SIGMA_TEST, loops=False) == TypeError_(K.UNBOUND, (0, 0, 1, 1), "nowhere")


def test_fits() -> None:
    assert fits(Dyn(), INT) is None
    assert fits(INT, Base("Log")) == K.MISMATCH
    assert fits(Bottom(), Arrow(INT, F(INT))) is None
    assert fits(Top(), Bottom()) == K.MISMATCH
    assert fits(Sum(Zero(), INT), Sum(INT, INT)) is None
    assert fits(Prod(One(), Dyn()), Prod(One(), INT)) is None


@pytest.mark.parametrize(("kind", "m"), CATALOGUE, ids=[kind for kind, _ in CATALOGUE])
def test_catalogue_entry_alone(kind: TypeErrorKind, m: Comp) -> None:
    error = run(m)
    assert error is not None
    assert error.kind == kind
