"""Hypothesis strategies for the CBPV IR: structural shapes (not typed)."""

from functools import cache

from hypothesis import strategies as st

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
