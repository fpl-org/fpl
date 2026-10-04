"""The surface AST: what was written, as frozen nodes, each with the Span it starts at.

A program is lines; a line is frames split by the bar, its comment, and the block indented under
it; a frame is cells split by tabs; a cell is items. Spans do not take part in equality.
"""

from dataclasses import dataclass, field
from typing import Literal

from fpl.errors import Span

type Kind = Literal["name", "number", "path", "modifier"]
type Pair = Literal["quotation", "prefix", "group", "dict"]


@dataclass(frozen=True)
class Word:
    """A token read by the affix pass: prefix sigil, kind, body (a path's segments, else one
    element) and suffix modifiers."""

    prefix: str
    kind: Kind
    body: tuple[str, ...]
    mods: str
    span: Span = field(compare=False)


@dataclass(frozen=True)
class Text:
    """A string: `str` holds text and the programs of its ⟨ ⟩ islands, `raw` one text."""

    kind: Literal["str", "raw"]
    parts: tuple["str | Program", ...]
    span: Span = field(compare=False)


@dataclass(frozen=True)
class Enclosure:
    """[ ] quotation, ( ) prefix, ⟨ ⟩ group or { } dict, holding frames."""

    pair: Pair
    frames: tuple["Frame", ...]
    span: Span = field(compare=False)


type Item = Word | Text | Enclosure


@dataclass(frozen=True)
class Cell:
    """Items between tabs."""

    items: tuple[Item, ...]
    span: Span = field(compare=False)


@dataclass(frozen=True)
class Frame:
    """Cells between bars; an empty frame starts where its enclosing node does."""

    cells: tuple[Cell, ...]
    span: Span = field(compare=False)


@dataclass(frozen=True)
class Comment:
    """A line comment, each of its lines as written from its mark on: a note (level 1, ⍝ counts
    as ;) after the code of its line, with the ; lines right under it that continue it, or a
    ;; ;;; ;;;; comment on a line of its own (level 2, 3, 4 ...)."""

    level: int
    lines: tuple[str, ...]
    span: Span = field(compare=False)


@dataclass(frozen=True)
class Line:
    """Frames on one line, its comment, and the lines of the block indented under it. A line of
    a ;; comment holds no frames; an empty line, one empty frame."""

    frames: tuple[Frame, ...]
    block: tuple["Line", ...]
    span: Span = field(compare=False)
    comment: Comment | None = None


@dataclass(frozen=True)
class Program:
    """The lines of a source, or of a string's island."""

    lines: tuple[Line, ...]
    span: Span = field(compare=False)
