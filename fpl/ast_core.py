"""The core AST: what desugaring leaves and evaluation reads.

A program is statements: a definition, or a line run on a fresh stack. Code is a tuple of nodes,
each a push of a value, a call of a word, a binder over the code in its scope, or a dict built
from its values. A value is a number, a string, a strand of those, a ⟨ ⟩ list, a quotation, a
symbol or a dict; a section is a quotation. EFFECTS declares each builtin's effect, the
same data an effect line gives a defined word; a word that runs a quotation declares a fixed
effect whatever the quotation does (hole control-effects).
"""

from dataclasses import KW_ONLY, dataclass, field
from decimal import Decimal
from typing import Literal

from fpl.errors import Span

type Number = int | Decimal
type Atom = Number | str
type Slot = Literal["value", "thunk", "code"]


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


@dataclass(frozen=True)
class Symbol:
    """#name: a name as a value."""

    name: str


@dataclass(frozen=True)
class Dict:
    """{ } once built: each key with its value, in the order written."""

    entries: tuple[tuple[str, "Value"], ...]


type Value = Atom | Strand | Listed | Quotation | Symbol | Dict


@dataclass(frozen=True)
class Push:
    """Push a value."""

    value: Value


@dataclass(frozen=True)
class Call:
    """Run a word, at the position it was written."""

    name: str
    span: Span = field(compare=False)


@dataclass(frozen=True)
class Bind:
    """→name: take the top and run the code of its scope with name standing for it. The scope
    is the rest of the line, the body or the quotation the binder is written in (decision f)."""

    name: str
    body: tuple["Node", ...]
    span: Span = field(compare=False)


@dataclass(frozen=True)
class Keyed:
    """{ key value ... }: each value's node run on a fresh stack, then one dict of them."""

    entries: tuple[tuple[str, "Node"], ...]
    span: Span = field(compare=False)


type Node = Push | Call | Bind | Keyed


@dataclass(frozen=True)
class Effect:
    """An effect line's names: what a word takes, then what it leaves; and the slot of each
    input (S49 rule 5): a value, run at once; a thunk, run when and if the word chooses; code,
    inspected, never run. No slots given means every input is a value; a count other than one
    per input is refused."""

    ins: tuple[str, ...]
    outs: tuple[str, ...]
    _: KW_ONLY
    slots: tuple[Slot, ...] = ()

    def __post_init__(self) -> None:
        slots = self.slots or ("value",) * len(self.ins)
        if len(slots) != len(self.ins):
            raise ValueError("one slot per input")
        object.__setattr__(self, "slots", slots)  # frozen: the default is filled once, here


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
    ",": Effect(("a", "b"), ("ab",), slots=("code", "code")),
    "!": Effect(("q",), ("x",), slots=("thunk",)),
    "if": Effect(("c", "t", "e"), (), slots=("value", "thunk", "thunk")),
    "swap-args": Effect(("x", "y", "q"), ("z",), slots=("value", "value", "thunk")),
    "repeat": Effect(("q", "n"), (), slots=("thunk", "value")),
    "each": Effect(("xs", "q"), ("ys",), slots=("value", "thunk")),
    "scan": Effect(("xs", "q"), ("ys",), slots=("value", "thunk")),
    "fold": Effect(("xs", "q"), ("x",), slots=("value", "thunk")),
}
