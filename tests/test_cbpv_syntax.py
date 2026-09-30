"""The IR's nodes: equality is structure, positions and origins aside; the invariants hold."""

from collections.abc import Callable, Iterator
from dataclasses import fields, is_dataclass, replace
from typing import cast

import icontract
import pytest
from cbpv_strategies import shapes
from hypothesis import given

from fpl.cbpv.syntax import (
    Case,
    Effects,
    F,
    LabelKey,
    Lam,
    One,
    Position,
    Prim,
    Program,
    Rec,
    Return,
    SplitPair,
    Thunk,
    To,
    Top,
    U,
    Unit,
)

MOVED = Position(7, 7)
UNKNOWN = cast("Effects", frozenset({"io"}))
UNIT = Return(Unit())


def children(x: object) -> tuple[object, ...]:
    """The fields of a node, or the items of a tuple; nothing for anything else."""
    if isinstance(x, tuple):
        return cast("tuple[object, ...]", x)
    if is_dataclass(x) and not isinstance(x, type):
        return tuple(getattr(x, f.name) for f in fields(x))
    return ()


def moved(x: object) -> object:
    """`x` with every `Prim.at` and `Thunk.origin` replaced, rebuilt through `__init__`."""
    items = children(x)
    if isinstance(x, tuple):
        return tuple(map(moved, items))
    if is_dataclass(x) and not isinstance(x, type):
        changes = {f.name: moved(v) for f, v in zip(fields(x), items, strict=True)}
        if isinstance(x, Prim):
            changes["at"] = MOVED
        if isinstance(x, Thunk):
            changes["origin"] = 7
        return replace(x, **changes)
    return x


def parts(x: object) -> Iterator[object]:
    """`x` and every node below it."""
    yield x
    for item in children(x):
        yield from parts(item)


@given(shapes())
def test_positions_ignored(node: object) -> None:
    """[law: positions-ignored] Every node `shapes()` draws equals, and hashes as, its copy with
    every `Position` and `Thunk.origin` replaced."""
    copy = moved(node)
    assert copy == node
    assert hash(copy) == hash(node)
    for part in parts(copy):
        if isinstance(part, Prim):
            assert part.at is not None
            assert (part.at.line, part.at.col) == (MOVED.line, MOVED.col)
        if isinstance(part, Thunk):
            assert part.origin == 7


VIOLATIONS: dict[str, Callable[[], object]] = {
    "lam name": lambda: Lam("", One(), 0, UNIT),
    "to name": lambda: To(UNIT, "", 0, UNIT),
    "split left": lambda: SplitPair(Unit(), "", 0, "y", 0, UNIT),
    "split right": lambda: SplitPair(Unit(), "x", 0, "", 0, UNIT),
    "case left": lambda: Case(Unit(), "", 0, UNIT, "y", 0, UNIT),
    "case right": lambda: Case(Unit(), "x", 0, UNIT, "", 0, UNIT),
    "rec name": lambda: Rec("", 0, F(One()), frozenset({"div"}), UNIT),
    "rec effect": lambda: Rec("f", 0, F(One()), UNKNOWN, UNIT),
    "thunk effect": lambda: U(Top(), UNKNOWN),
    "prim effect": lambda: Prim("p", Top(), UNKNOWN, None),
    "label ordinal": lambda: LabelKey("w", -1),
    "defs distinct": lambda: Program((("x", Unit()), ("x", Unit())), ()),
}


@pytest.mark.parametrize("build", VIOLATIONS.values(), ids=VIOLATIONS.keys())
def test_invariant_refuses(build: Callable[[], object]) -> None:
    with pytest.raises(icontract.ViolationError):
        build()
