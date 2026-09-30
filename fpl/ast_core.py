"""The core AST: what desugaring leaves and evaluation reads.

A program is statements: a definition, or a line run on a fresh stack. Code is a tuple of nodes,
each a push of a value, a call of a word, a binder over the code in its scope, or a dict built
from its values. A value is a number, a string, a strand of those, a ⟨ ⟩ list, a quotation, a
symbol or a dict; a section is a quotation. EFFECTS declares each builtin's effect, the
same data an effect line gives a defined word; a word that runs a quotation declares a fixed
effect whatever the quotation does (hole control-effects); ? and _ declare none, the elaborator
finding what fills them (hole goal-placeholder).
"""

from dataclasses import KW_ONLY, dataclass, field
from decimal import Decimal
from typing import Literal

from fpl.errors import Span

type Number = int | Decimal
type Atom = Number | str
type Slot = Literal["value", "thunk", "code"]

DIGITS = 4096
"""How many digits a numeral may have, its sign and point not counted, and how many a computed
number may have before its point (hole number-bound): under Python's 4300-digit limit on
converting between int and str, so a number always reads and prints, never a ValueError."""


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


@dataclass(frozen=True)
class Wild:
    """_ : matches anything and binds nothing."""


@dataclass(frozen=True)
class Var:
    """A name in a pattern: matches anything and names it in the row's body."""

    name: str


@dataclass(frozen=True)
class Equal:
    """A literal, or $x: matches a value equal to the one the node pushes once x is bound."""

    node: "Node"


@dataclass(frozen=True)
class Inverse:
    """( name args ): the constructor run backwards, each argument matching what it gave."""

    name: str
    args: tuple["Pattern", ...]
    span: Span = field(compare=False)


@dataclass(frozen=True)
class Guarded:
    """p ∈ test: p, and the word test leaves 1 on the value."""

    pattern: "Pattern"
    test: str
    span: Span = field(compare=False)


type Pattern = Wild | Var | Equal | Inverse | Guarded


@dataclass(frozen=True)
class Row:
    """One pattern per value a match takes, then the code run when they all match."""

    patterns: tuple[Pattern, ...]
    body: tuple["Node", ...]


@dataclass(frozen=True)
class Match:
    """Take as many values as a row has patterns and run the body of the first row matching
    them; none is +fail, raised at the match."""

    rows: tuple[Row, ...]
    span: Span = field(compare=False)


@dataclass(frozen=True)
class Refuse:
    """An error where it runs, never +fail: a call two crossing clauses both fit (design 09
    §3.4)."""

    message: str
    span: Span = field(compare=False)


type Node = Push | Call | Bind | Keyed | Match | Refuse


@dataclass(frozen=True)
class Effect:
    """An effect line's names: what a word takes, then what it leaves, and whether it may fail
    (+fail); and the slot of each input (S49 rule 5): a value, run at once; a thunk, run when and
    if the word chooses; code, inspected, never run; and the type of each, a type word's name,
    None for an untyped slot. No slots given means every input is a value, no types that every
    input is untyped; a count other than one per input is refused."""

    ins: tuple[str, ...]
    outs: tuple[str, ...]
    fails: bool = False
    _: KW_ONLY
    slots: tuple[Slot, ...] = ()
    types: tuple[str | None, ...] = ()

    def __post_init__(self) -> None:
        """Fill the default slots, one value per input, and refuse a count that does not match."""
        slots = self.slots or ("value",) * len(self.ins)
        types = self.types or (None,) * len(self.ins)
        if len(slots) != len(self.ins):
            raise ValueError("one slot per input")
        if len(types) != len(self.ins):
            raise ValueError("one type per input")
        object.__setattr__(self, "slots", slots)  # frozen: the default is filled once, here
        object.__setattr__(self, "types", types)


@dataclass(frozen=True)
class Define:
    """name : ins -- outs, the code of the block under it, its docstring ("" for none), and where
    its effect line is; and the clause it is of a dispatched word: () for a word not
    dispatched, (n,) for the dispatcher of its arity-n clauses, whose words `clauses` lists in
    written order, and (n, i) for its i-th clause of arity n."""

    name: str
    effect: Effect
    code: tuple[Node, ...]
    doc: str = ""
    span: Span = field(compare=False, default=Span(1, 1))
    clause: tuple[int, ...] = ()
    clauses: tuple[str, ...] = ()

    @property
    def word(self) -> str:
        """What calls it and what its queries hang under: the name, then the clause."""
        return "/".join((self.name, *map(str, self.clause)))

    @property
    def paths(self) -> tuple[str, ...]:
        """The name, then each longer prefix of the word, the word last."""
        return tuple(
            "/".join((self.name, *map(str, self.clause[:end])))
            for end in range(len(self.clause) + 1)
        )


@dataclass(frozen=True)
class Run:
    """A line's code, run on a fresh stack; what it leaves is printed; and where the line is."""

    code: tuple[Node, ...]
    span: Span = field(compare=False, default=Span(1, 1))


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
    "pair": Effect(("a", "b"), ("p",)),
    "cons": Effect(("x", "xs"), ("ys",)),
    "!": Effect(("q",), ("x",), slots=("thunk",)),
    "if": Effect(("c", "t", "e"), (), slots=("value", "thunk", "thunk")),
    "swap-args": Effect(("x", "y", "q"), ("z",), slots=("value", "value", "thunk")),
    "repeat": Effect(("q", "n"), (), slots=("thunk", "value")),
    "each": Effect(("xs", "q"), ("ys",), slots=("value", "thunk")),
    "scan": Effect(("xs", "q"), ("ys",), slots=("value", "thunk")),
    "fold": Effect(("xs", "q"), ("x",), slots=("value", "thunk")),
    **dict.fromkeys(("Int", "Decimal", "Text", "Symbol"), Effect(("x",), ("b",))),
    "?": Effect((), ()),
    "_": Effect((), ()),
}
