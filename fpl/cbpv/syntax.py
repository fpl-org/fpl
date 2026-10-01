"""The IR's terms and types as frozen values: Levy's CBPV with `op`, `fail`, `rec`, `label`.

Promised: every node is a frozen dataclass (`slots` unless it has an invariant: icontract
cannot wrap the `__setstate__` a slotted dataclass generates), compared and hashed by structure
only; source positions (`Prim.at`) and a thunk's origin (`Thunk.origin`) ride along without
entering equality, so two nodes that differ only there are equal. Names are compared as written (no
alpha-equivalence). Refused at construction (icontract `ViolationError`): an empty binder name, an
effect outside `{div, fail}`, a negative label ordinal. A program defining a name twice is built:
the checker refuses it (`DUPLICATE_DEF`).
"""

from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass, field
from typing import Literal

import icontract

type Eff = Literal["div", "fail"]
type Effects = frozenset[Eff]
type Grade = Literal[0, 1, "ω"]

KNOWN: Effects = frozenset({"div", "fail"})


def binder_named(self: To | Lam | Rec) -> bool:
    """A binder binds a name one can write."""
    return self.name != ""


def pair_named(self: SplitPair) -> bool:
    """Both binders of `pm V as (x, y)` bind names one can write."""
    return "" not in (self.left, self.right)


def case_named(self: Case) -> bool:
    """Both binders of `pm V as {inl x | inr y}` bind names one can write."""
    return "" not in (self.left_name, self.right_name)


def effects_known(self: U | Rec | Prim) -> bool:
    """An effect set is a subset of the statement's `{div, fail}`."""
    return self.eff <= KNOWN


def ordinal_natural(self: LabelKey) -> bool:
    """A label's ordinal counts from 0."""
    return self.ordinal >= 0


@dataclass(frozen=True, slots=True)
class Position:
    """A source position the lowering keeps for a constant's panic."""

    line: int
    col: int


# Value types.


@dataclass(frozen=True, slots=True)
class Base:
    """A base type the signature declares (`Int`, `Log`; the walker's `Num`, `Text`, `Sym`)."""

    name: str


@dataclass(frozen=True, slots=True)
class Dyn:
    """The walker's untracked sort: consistent with every base type, and nothing else."""


@dataclass(frozen=True, slots=True)
class One:
    """The unit type `1`."""


@dataclass(frozen=True, slots=True)
class Zero:
    """The empty type `0`."""


@dataclass(frozen=True, slots=True)
class Prod:
    """`A * A'`."""

    left: VType
    right: VType


@dataclass(frozen=True, slots=True)
class Sum:
    """`A + A'`."""

    left: VType
    right: VType


@icontract.invariant(effects_known)
@dataclass(frozen=True)
class U:
    """`U_ε B`: a thunk of `B` whose forcing may have the effects `ε` (hole thunk-effect)."""

    comp: CType
    eff: Effects


# Computation types.


@dataclass(frozen=True, slots=True)
class F:
    """`F A`: a computation that returns an `A`."""

    value: VType


@dataclass(frozen=True, slots=True)
class Arrow:
    """`A → B`: pops an `A`, then behaves as `B`."""

    arg: VType
    res: CType


@dataclass(frozen=True, slots=True)
class Top:
    """`Top`, the empty product of computations."""


@dataclass(frozen=True, slots=True)
class With:
    """`B & B'`."""

    left: CType
    right: CType


# Values.


@dataclass(frozen=True, slots=True)
class Var:
    """A variable."""

    name: str


@dataclass(frozen=True, slots=True)
class Const:
    """A literal: an opaque hashable value at a base type."""

    value: Hashable
    type: VType


@dataclass(frozen=True, slots=True)
class Unit:
    """`()`."""


@dataclass(frozen=True, slots=True)
class Pair:
    """`(V, W)`."""

    left: Value
    right: Value


@dataclass(frozen=True, slots=True)
class Inl:
    """`inl V`, annotated with the right summand."""

    value: Value
    right: VType


@dataclass(frozen=True, slots=True)
class Inr:
    """`inr V`, annotated with the left summand."""

    value: Value
    left: VType


@dataclass(frozen=True, slots=True)
class Thunk:
    """`thunk M`; `origin` indexes the lowering's table of source quotations."""

    body: Comp
    origin: int | None = field(default=None, compare=False)


# Computations.


@dataclass(frozen=True, slots=True)
class Return:
    """`return V`."""

    value: Value


@icontract.invariant(binder_named)
@dataclass(frozen=True)
class To:
    """`M to x. N`."""

    bound: Comp
    name: str
    grade: Grade
    body: Comp


@dataclass(frozen=True, slots=True)
class Force:
    """`force V`."""

    value: Value


@icontract.invariant(binder_named)
@dataclass(frozen=True)
class Lam:
    """`λx:A. M`."""

    name: str
    type: VType
    grade: Grade
    body: Comp


@dataclass(frozen=True, slots=True)
class App:
    """`V ` M`: push `V`, run `M`."""

    arg: Value
    fun: Comp


@icontract.invariant(pair_named)
@dataclass(frozen=True)
class SplitPair:
    """`pm V as (x, y). M`."""

    value: Value
    left: str
    left_grade: Grade
    right: str
    right_grade: Grade
    body: Comp


@icontract.invariant(case_named)
@dataclass(frozen=True)
class Case:
    """`pm V as {inl x. M | inr y. N}`."""

    value: Value
    left_name: str
    left_grade: Grade
    left: Comp
    right_name: str
    right_grade: Grade
    right: Comp


@dataclass(frozen=True, slots=True)
class Absurd:
    """`pm V as {}` at `B`, for `V : 0`."""

    value: Value
    type: CType


@dataclass(frozen=True, slots=True)
class Both:
    """`⟨M, N⟩`."""

    left: Comp
    right: Comp


@dataclass(frozen=True, slots=True)
class First:
    """`fst M`."""

    comp: Comp


@dataclass(frozen=True, slots=True)
class Second:
    """`snd M`."""

    comp: Comp


@icontract.invariant(binder_named)
@icontract.invariant(effects_known)
@dataclass(frozen=True)
class Rec:
    """`rec x : U_ε B. M`."""

    name: str
    grade: Grade
    type: CType
    eff: Effects
    body: Comp


@dataclass(frozen=True, slots=True)
class Op:
    """`op V W`: the operation `op` of the capability `V`, with argument `W`."""

    op: str
    cap: Value
    arg: Value


@dataclass(frozen=True, slots=True)
class Fail:
    """`fail W`."""

    payload: Value


@icontract.invariant(ordinal_natural)
@dataclass(frozen=True)
class LabelKey:
    """A label's key: the definition's path (or "line N") and an ordinal (hole label-keys)."""

    word: str
    ordinal: int


@dataclass(frozen=True, slots=True)
class Label:
    """`label l. M`: emits `l`, then runs `M`."""

    label: LabelKey
    body: Comp


@icontract.invariant(effects_known)
@dataclass(frozen=True)
class Prim:
    """A constant at one instance of its type; `at` is its call site."""

    name: str
    type: CType
    eff: Effects
    at: Position | None = field(compare=False)


@dataclass(frozen=True, slots=True)
class Program:
    """Top-level definitions, each a closed value over those before it, and the runs."""

    defs: tuple[tuple[str, Value], ...]
    runs: tuple[Comp, ...]


type VType = Base | Dyn | One | Zero | Prod | Sum | U
type CType = F | Arrow | Top | With
type Type = VType | CType
type Value = Var | Const | Unit | Pair | Inl | Inr | Thunk
type Comp = (
    Return | To | Force | Lam | App | SplitPair | Case | Absurd | Both | First | Second | Rec
) | (Op | Fail | Label | Prim)
type Node = Type | Value | Comp | LabelKey | Program
