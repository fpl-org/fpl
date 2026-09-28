"""The core AST: what desugaring leaves and evaluation reads.

A program is statements: a definition, or a line run on a fresh stack. Code is a tuple of nodes,
each a push of a value or a call of a word. A value is a number, a string, a strand of those, a
⟨ ⟩ list, or a quotation; a section is a quotation. EFFECTS declares each builtin's effect, the
same data an effect line gives a defined word.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from fpl.errors import Span

type Number = int | Decimal
type Atom = Number | str


@dataclass(frozen=True)
class Strand:
    """Literals written side by side in one cell: one value."""

    items: tuple[Atom, ...]


@dataclass(frozen=True)
class Listed:
    """A ⟨ ⟩ list: its items in order."""

    items: tuple["Value", ...]


@dataclass(frozen=True)
class Quotation:
    """Code as a value."""

    code: tuple["Node", ...]


type Value = Atom | Strand | Listed | Quotation


@dataclass(frozen=True)
class Push:
    """Push a value."""

    value: Value


@dataclass(frozen=True)
class Call:
    """Run a word, at the position it was written."""

    name: str
    span: Span = field(compare=False)


type Node = Push | Call


@dataclass(frozen=True)
class Effect:
    """An effect line's names: what a word takes, then what it leaves."""

    ins: tuple[str, ...]
    outs: tuple[str, ...]


@dataclass(frozen=True)
class Define:
    """name : ins -- outs, and the code of the block under it."""

    name: str
    effect: Effect
    code: tuple[Node, ...]


@dataclass(frozen=True)
class Run:
    """A line's code, run on a fresh stack; what it leaves is printed."""

    code: tuple[Node, ...]


type Statement = Define | Run

_BINARY = Effect(("x", "y"), ("z",))
EFFECTS: dict[str, Effect] = {
    "+": _BINARY,
    "-": _BINARY,
    "times": _BINARY,
    "swap": Effect(("x", "y"), ("y", "x")),
    "dup": Effect(("x",), ("x", "x")),
    "drop": Effect(("x",), ()),
    "enclose": Effect(("x",), ("q",)),
    ",": Effect(("a", "b"), ("ab",)),
}
