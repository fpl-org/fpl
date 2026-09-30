"""The printer: Levy's notation, injective on structure."""

from dataclasses import fields, replace
from typing import Any, cast

import pytest
from cbpv_strategies import shapes
from hypothesis import given
from test_cbpv_check import SYNTAX

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
    Value,
    Var,
    VType,
    With,
    Zero,
)
from fpl.cbpv.text import print as text

INT = Base("Int")


@given(shapes(), shapes())
def test_print_injective(a: Node, b: Node) -> None:
    """[law: print-injective] Two structurally different nodes `shapes()` draws print to
    different text."""
    if a != b:
        assert text(a) != text(b)


def test_one_binder_per_line() -> None:
    body = Label(LabelKey("w", 0), Lam("n", INT, 1, Return(Var("n"))))
    rec = Rec("f", "ω", Arrow(INT, F(INT)), frozenset({"div"}), body)
    assert text(rec).splitlines() == [
        "rec f :ω U{div} (Int → (F Int)).",
        "(label &'w'#0.",
        "(λn :1 Int.",
        "(return n)))",
    ]


def test_program_lists_defs_then_runs() -> None:
    program = Program((("k", Const(3, INT)),), (Return(Var("k")),))
    assert text(program) == "k = (3 : Int)\nrun (return k)"


def test_projections_print_their_side() -> None:
    """Fixed, so coverage does not wait on `shapes()` drawing a `fst` or a `snd`."""
    assert text(First(Return(Var("x")))) == "fst (return x)"
    assert text(Second(Return(Var("x")))) == "snd (return x)"


def test_sequencing_prints_its_bound_name_and_grade() -> None:
    """Fixed, so coverage does not wait on `shapes()` drawing a `to`."""
    printed = text(To(Return(Var("x")), "y", "ω", Return(Var("y"))))
    assert printed == "(return x) to y :ω.\n(return y)"


KEY = LabelKey("w", 0)
BODY = Return(Var("x"))
SAMPLES: tuple[Node, ...] = (
    INT, Dyn(), One(), Zero(), Prod(INT, One()), Sum(INT, One()), U(F(INT), frozenset({"div"})),
    F(INT), Arrow(INT, F(INT)), Top(), With(F(INT), Top()),
    Var("x"), Const(3, INT), Unit(), Pair(Var("x"), Unit()), Inl(Var("x"), INT),
    Inr(Var("x"), INT), Thunk(BODY),
    BODY, To(BODY, "y", 1, Return(Var("y"))), Force(Var("x")), Lam("x", INT, 1, BODY),
    App(Var("x"), BODY), SplitPair(Var("p"), "x", 1, "y", 0, BODY),
    Case(Var("s"), "x", 1, BODY, "y", 0, Return(Var("y"))), Absurd(Var("z"), F(INT)),
    Both(BODY, Return(Unit())), First(BODY), Second(BODY),
    Rec("f", "ω", F(INT), frozenset({"div"}), BODY), Op("emit", Var("h"), Var("x")),
    Fail(Var("x")), KEY, Label(KEY, BODY), Prim("add", Arrow(INT, F(INT)), frozenset(), None),
    Program((("k", Unit()),), (BODY,)),
)  # fmt: skip
CATEGORIES = (VType.__value__, CType.__value__, Value.__value__, Comp.__value__, LabelKey)


def _other_node(node: Node) -> Node:
    """The first sample of `node`'s category that differs from it (a second label key)."""
    category = next(c for c in CATEGORIES if isinstance(node, c))
    return next(s for s in (*SAMPLES, LabelKey("v", 1)) if isinstance(s, category) and s != node)


def other(value: object) -> object:
    """A value of `value`'s kind that differs from it; a position or origin comes back as is."""
    match value:
        case str():
            return f"{value}'"
        case int():
            return value + 1
        case frozenset():
            return value ^ {"fail"}  # pyright: ignore[reportUnknownVariableType] -- an effect set
        case tuple():
            return value[:-1]  # pyright: ignore[reportUnknownVariableType] -- defs or runs
        case None:
            return None
        case _:
            return _other_node(cast(Node, value))


def test_one_sample_per_class() -> None:
    """Fixed, so every printer rule runs on every run, whatever `shapes()` draws."""
    assert [type(n) for n in SAMPLES] == list(dict.fromkeys(type(n) for n in SAMPLES))
    assert {type(n) for n in SAMPLES} == SYNTAX


@pytest.mark.parametrize("node", SAMPLES, ids=[type(n).__name__ for n in SAMPLES])
def test_every_compared_field_prints(node: Node) -> None:
    """A copy of `node` with one field changed that compares unequal prints differently."""
    for f in fields(node):
        changes: dict[str, Any] = {f.name: other(getattr(node, f.name))}
        changed = replace(node, **changes)
        if changed != node:
            assert text(changed) != text(node), f.name
