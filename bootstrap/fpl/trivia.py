"""Comments by level, read off the tree: the level is bound to position (S33, as in Lisp).

;    after code on its line (⍝ counts as ;)   its line (trailing)
;;   on a line of its own                      the next code line (before); a doc when that line
                                               is a definition head, or when the ;; opens a
                                               head's body (SHAR gram/test_fpl.py comments())
;;;  on a line of its own                      a section of the file
;;;; on a line of its own                      the file
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

from fpl.ast_surface import Line, Program, Word

type Attachment = Literal["trailing", "before", "doc", "section", "file"]
KINDS: tuple[Attachment, ...] = ("trailing", "before", "section", "file")


@dataclass(frozen=True)
class Attached:
    """A comment classified: its source line, level, attachment, the source line it attaches to
    (None for a section or the file, or a ;; before no code), and its text without marks."""

    line: int
    level: int
    kind: Attachment
    target: int | None
    text: str


def head(line: Line) -> bool:
    """A definition head: its first cell's second item is the plain word `:`."""
    cells = line.frames[0].cells if line.frames else ()
    second = [item for cell in cells[:1] for item in cell.items[1:2]]
    return second == [Word("", "name", (":",), "", second[0].span)] if second else False


def code(line: Line) -> bool:
    """A line holds code: a bar, or an item in a frame."""
    return len(line.frames) > 1 or any(frame.cells for frame in line.frames)


def _order(lines: tuple[Line, ...], parent: Line | None) -> Iterator[tuple[Line, Line | None]]:
    """Lines in the order they are written, each with the line whose block holds it."""
    for line in lines:
        yield line, parent
        yield from _order(line.block, line)


type Order = tuple[tuple[Line, Line | None], ...]


def _aimed(order: Order, n: int) -> tuple[Attachment, int | None]:
    """Where the ;; on line n of the order points: the next code line, as a doc when it is a
    head; else, when the ;; opens a head's body, that head as a doc."""
    after = next((line for line, _ in order[n + 1 :] if code(line)), None)
    if after is not None and head(after):
        return "doc", after.span.line
    opened = _opens(order, n)
    if opened is not None:
        return "doc", opened.span.line
    return "before", None if after is None else after.span.line


def _opens(order: Order, n: int) -> Line | None:
    """The head whose body the line n of the order opens, before any code of it."""
    before = next((line for line, _ in reversed(order[:n]) if code(line)), None)
    parent = order[n][1]
    return parent if parent is not None and before is parent and head(parent) else None


def comments(program: Program) -> tuple[Attached, ...]:
    """Every comment of a program, classified by its level. A string holds none."""
    order = tuple(_order(program.lines, None))
    found: list[Attached] = []
    for n, (line, _) in enumerate(order):
        if line.comment is None:
            continue
        kind = KINDS[min(line.comment.level, len(KINDS)) - 1]
        target = line.span.line if kind == "trailing" else None
        if kind == "before":
            kind, target = _aimed(order, n)
        text = " ".join(part.lstrip(";⍝").strip() for part in line.comment.lines)
        found.append(Attached(line.comment.span.line, line.comment.level, kind, target, text))
    return tuple(found)


def docstrings(program: Program) -> dict[int, str]:
    """Each documented head's docstring, by its source line: its docs in order, a line each."""
    docs: dict[int, list[str]] = {}
    for comment in comments(program):
        if comment.kind == "doc" and comment.target is not None:
            docs.setdefault(comment.target, []).append(comment.text)
    return {line: "\n".join(texts) for line, texts in docs.items()}
