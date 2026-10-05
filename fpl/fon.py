"""FON data: the inert, braced data profile of FPL, read within bounds and written canonically.

The reader never evaluates, resolves or constructs typed objects: a bare name or #name is a
symbol, $name or $<code>:<n> a reference by identity, &<multihash> a reference by content
(fpl/multihash.py, the hex alias read too), [ ] opaque code, ( ) a tagged tuple, { } a dict
with literal keys, a number an exact decimal and _ absence. Whitespace separates tokens only,
in any amount; there are no comments, blocks or islands. Strings are counted by the code
grammar's pre-lexer. Depth, token length and input size are parameters.
"""

import contextlib
import math
import re
import struct
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from functools import cache
from typing import assert_never

from lark import Lark, Token, Tree, UnexpectedInput

from fpl.errors import FplError, Span
from fpl.lex import Lines, Prelexed, pairs
from fpl.multihash import Multihash, spelling

GRAMMAR = r"""
start: value*
?value: TOKEN | list | dict | tuple | code
list:  "⟨" value* "⟩"
dict:  "{" (TOKEN value)* "}"
tuple: "(" value* ")"
code:  "[" value* "]"
TOKEN: /[^\s\[\]()“”「」⟦⟧⟨⟩{}|⍝]+/
%ignore /\s+/
"""
STRINGS = re.compile(r"[“「⟦”」⟧]")
OPENERS = {"[": "]", "(": ")", "⟨": "⟩", "{": "}"}
NUMBER = re.compile(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?")
NUMERIC = re.compile(r"-?(0x|[0-9])")
HEXFLT = re.compile(r"-?0x(0|1)(\.[0-9a-f]*[1-9a-f])?p-?(0|[1-9][0-9]*)")
TOKEN = re.compile(r"[^\s\[\]()“”「」⟦⟧⟨⟩{}|⍝¶]+")


@dataclass(frozen=True)
class Absent:
    """_ : nothing here."""

    def written(self) -> str:
        """Canonical FON."""
        return "_"


@dataclass(frozen=True)
class Bool:
    """true or false, a kind apart from numbers."""

    value: bool

    def written(self) -> str:
        """Canonical FON."""
        return "true" if self.value else "false"


@dataclass(frozen=True)
class Num:
    """An exact decimal: no +, no leading zeros, no exponent."""

    value: Decimal

    def written(self) -> str:
        """Canonical FON."""
        return format(self.value, "f")


@dataclass(frozen=True)
class Flt:
    """An IEEE binary64 float, held as its bit pattern so that every float, nan and -0.0
    included, equals only itself; written as C99 %a hex, exact."""

    bits: int

    @classmethod
    def of(cls, value: float) -> "Flt":
        """The float's bit pattern."""
        return cls(int(struct.unpack("<q", struct.pack("<d", value))[0]))

    @property
    def value(self) -> float:
        """The float the bits spell."""
        return float(struct.unpack("<d", struct.pack("<q", self.bits))[0])

    def written(self) -> str:
        """Canonical FON: nan, -nan, ∞, -∞ or the shortest %a spelling."""
        x = self.value
        sign = "-" if math.copysign(1, x) < 0 else ""
        if math.isnan(x):
            return sign + "nan"
        if math.isinf(x):
            return sign + "∞"
        mantissa, exponent = x.hex().split("p")
        return mantissa.rstrip("0").rstrip(".") + "p" + exponent.replace("+", "")


@dataclass(frozen=True)
class Sym:
    """A symbol: a bare name, or #name; not resolved."""

    name: str

    def written(self) -> str:
        """Canonical FON."""
        return self.name


@dataclass(frozen=True)
class Cell:
    """$name, or $<code>:<n> naming by hash: a reference by identity; not followed."""

    name: str | Multihash

    def written(self) -> str:
        """Canonical FON."""
        return "$" + (self.name.spelled() if isinstance(self.name, Multihash) else self.name)


@dataclass(frozen=True)
class Hash:
    """&<multihash>: a reference by content, the bytes themselves up to 32; not followed."""

    ref: Multihash

    def written(self) -> str:
        """Canonical FON: the decimal spelling."""
        return "&" + self.ref.spelled()


@dataclass(frozen=True)
class Str:
    """“…” text, interpolation kept as text, or 「…」 raw text."""

    text: str
    raw: bool = False

    def written(self) -> str:
        """Canonical FON."""
        return f"「{self.text}」" if self.raw else f"“{self.text}”"


@dataclass(frozen=True)
class List:
    """⟨ … ⟩ values."""

    items: tuple["Value", ...]

    def written(self) -> str:
        """Canonical FON; the empty list is ⟨⟩."""
        return f"⟨ {_spaced(self.items)} ⟩" if self.items else "⟨⟩"


@dataclass(frozen=True)
class Tagged:
    """( … ): a tagged tuple; its head is data, never called."""

    items: tuple["Value", ...]

    def written(self) -> str:
        """Canonical FON."""
        return f"( {_spaced(self.items)} )" if self.items else "( )"


@dataclass(frozen=True)
class Code:
    """[ … ]: code, opaque to the reader."""

    items: tuple["Value", ...]

    def written(self) -> str:
        """Canonical FON."""
        return f"[ {_spaced(self.items)} ]" if self.items else "[ ]"


type Leaf = Absent | Bool | Num | Flt | Sym | Cell | Hash | Str


@dataclass(frozen=True)
class Dict:
    """{ key value … }: keys literal and distinct, in the order written."""

    entries: tuple[tuple[Leaf, "Value"], ...]

    def written(self) -> str:
        """Canonical FON."""
        body = " ".join(f"{key.written()} {value.written()}" for key, value in self.entries)
        return f"{{ {body} }}" if self.entries else "{ }"


type Value = Leaf | List | Tagged | Code | Dict
type Json = bool | int | float | str | list["Json"] | dict[str, "Json"] | None
SEQUENCES: dict[str, Callable[[tuple[Value, ...]], Value]] = {
    "list": List,
    "tuple": Tagged,
    "code": Code,
}

CONSTANTS: dict[str, Leaf] = {
    "_": Absent(),
    "true": Bool(True),
    "false": Bool(False),
    "∞": Flt.of(math.inf),
    "-∞": Flt.of(-math.inf),
    "nan": Flt.of(math.nan),
    "-nan": Flt.of(-math.nan),
}


def _spaced(values: tuple[Value, ...]) -> str:
    """Values separated by one space."""
    return " ".join(value.written() for value in values)


class _RefusedError(Exception):
    """A token the profile refuses, before it is placed in the source."""


def _hash(text: str) -> Hash:
    """&<multihash>, in decimal or the hex alias, inline bytes allowed."""
    try:
        return Hash(spelling(text, inline=True))
    except ValueError:
        raise _RefusedError(f"malformed hash reference &{text}") from None


def _cell(text: str) -> Cell:
    """$name, or $<code>:<n> when it opens with a digit; no hex alias, which would read as a
    name, and no inline bytes, which are content, not identity."""
    if text[0] not in "0123456789":
        return Cell(text)
    if ":" in text:
        with contextlib.suppress(ValueError):
            return Cell(spelling(text, inline=False))
    raise _RefusedError(f"malformed identity ${text}")


def _hexflt(token: str) -> Flt:
    """A hex float, read only in the spelling Flt.written gives it: a second spelling of the
    same bits (0x0.8p0 for 0x1p-1, 0x0p5 for 0x0p0) or one that rounds or underflows
    (0x1p-2000) is refused, so that write ∘ read is the identity on what reads, as it is for
    decimals; past binary64 (0x1p2000) is out of range."""
    try:
        flt = Flt.of(float.fromhex(token))
    except OverflowError:
        raise _RefusedError(f"float out of range {token}") from None
    if flt.written() != token:
        raise _RefusedError(f"non-canonical number {token}")
    return flt


SIGILS: dict[str, Callable[[str], Leaf]] = {"$": _cell, "&": _hash, "#": Sym}


def leaf(token: str) -> Leaf:
    """The value one token spells; a number or hash out of canonical form is refused."""
    constant = CONSTANTS.get(token)
    if constant is not None:
        return constant
    if HEXFLT.fullmatch(token):
        return _hexflt(token)
    if NUMBER.fullmatch(token):
        return Num(Decimal(token))
    if NUMERIC.match(token):
        raise _RefusedError(f"non-canonical number {token}")
    sigil = SIGILS.get(token[0]) if len(token) > 1 else None
    return Sym(token) if sigil is None else sigil(token[1:])


@cache
def parser() -> Lark:
    """The LALR parser of the braced profile."""
    return Lark(GRAMMAR, parser="lalr")


class _Build:
    """Values from Lark's tree, every refusal placed in the source."""

    def __init__(self, text: str, lexed: Prelexed, max_token: int) -> None:
        self.text, self.lexed, self.max_token = text, lexed, max_token

    def at(self, offset: int) -> Span:
        """The source position of a code offset."""
        return Lines(self.text).span(self.lexed.origin[offset])

    def leaf(self, token: Token) -> Leaf:
        """A token's value: a stashed string, or what the token spells."""
        start = token.start_pos or 0
        stashed = self.lexed.stash.get(start)
        if stashed is not None:
            return Str(self.text[stashed.start : stashed.end], stashed.kind == "raw")
        if len(token) > self.max_token:
            raise FplError(self.at(start), "token too long")
        try:
            return leaf(str(token))
        except _RefusedError as refusal:
            raise FplError(self.at(start), str(refusal)) from None

    def value(self, node: Tree[Token] | Token) -> Value:
        """A value from a token or an enclosure."""
        if isinstance(node, Token):
            return self.leaf(node)
        if node.data == "dict":
            return self.dict(node.children)
        items = tuple(self.value(child) for child in node.children)
        return SEQUENCES[str(node.data)](items)

    def dict(self, children: list[Tree[Token] | Token]) -> Dict:
        """Keys and values in turn; a key given twice is refused where it repeats."""
        entries: dict[Leaf, Value] = {}
        for key_token, node in zip(children[::2], children[1::2], strict=True):
            assert isinstance(key_token, Token)
            key = self.leaf(key_token)
            if key in entries:
                raise FplError(self.at(key_token.start_pos or 0), f"repeated key {key.written()}")
            entries[key] = self.value(node)
        return Dict(tuple(entries.items()))


def _depth(text: str, lexed: Prelexed, max_depth: int) -> None:
    """Refuse an enclosure opened deeper than max_depth, or one never closed, by a linear scan
    of the code; a closer out of turn is left to the grammar."""
    open_: list[int] = []
    for offset, char in enumerate(lexed.code):
        if char in OPENERS:
            open_.append(offset)
        elif open_ and char == OPENERS[lexed.code[open_[-1]]]:
            open_.pop()
        if len(open_) > max_depth:
            raise FplError(Lines(text).span(lexed.origin[offset]), "nesting too deep")
    if open_:
        char = lexed.code[open_[-1]]
        raise FplError(Lines(text).span(lexed.origin[open_[-1]]), f"{char} never closed")


def _placed(lines: Lines, lexed: Prelexed, offset: int | None) -> Span:
    """The source position of Lark's failure; an unknown or end position is the text's end."""
    return lines.span(lexed.origin[offset if offset is not None and offset >= 0 else -1])


def read(text: str, max_depth: int = 64, max_token: int = 4096, max_size: int = 1 << 24) -> Value:
    """The value a FON document spells: one value is itself, several or none a List of them.
    Linear and total: every refusal is an FplError inside the text, bounds included."""
    lines = Lines(text)
    if len(text) > max_size:
        raise FplError(lines.span(max_size), "input too large")
    lexed = pairs(text, special=STRINGS)
    _depth(text, lexed, max_depth)
    try:
        tree = parser().parse(lexed.code)  # pyright: ignore[reportUnknownMemberType] -- lark types its text argument loosely
    except UnexpectedInput as failure:
        raise FplError(_placed(lines, lexed, failure.pos_in_stream), "unexpected input") from None
    values = tuple(_Build(text, lexed, max_token).value(child) for child in tree.children)
    return values[0] if len(values) == 1 else List(values)


def write(value: Value) -> str:
    """Canonical FON for a value, the text `read` gives it back from. A text holding an
    unbalanced “ or 「, or a symbol spelling another kind, has no FON spelling (HOLES.md:
    fon-unwritable)."""
    return value.written()


def embed(json: Json) -> Value:
    """A JSON value as FON: null is absence, a number an exact decimal, an object a Dict keyed
    by symbols where the key reads back as one, else by text."""
    match json:
        case list():
            return List(tuple(embed(item) for item in json))
        case dict():
            return Dict(tuple((_key(key), embed(item)) for key, item in json.items()))
        case _:
            return _scalar(json)


def _scalar(json: bool | float | str | None) -> Leaf:
    """A JSON scalar as FON."""
    match json:
        case None:
            return Absent()
        case bool():
            return Bool(json)
        case int() | float():
            return Num(Decimal(repr(json)))
        case str():
            return Str(json)
        case _:
            assert_never(json)


def _key(name: str) -> Leaf:
    """A JSON key as a symbol when it spells one, else as text."""
    return Sym(name) if TOKEN.fullmatch(name) and _spells(name) == Sym(name) else Str(name)


def _spells(token: str) -> Leaf | None:
    """What a token reads as, or None when refused."""
    try:
        return leaf(token)
    except _RefusedError:
        return None
