"""Comments by level, read off the tree: the level is bound to position (S33, as in Lisp).

;    after code on its line (⍝ counts as ;)   its line (trailing)
;;   on a line of its own                      the next code line (doc)
;;;  on a line of its own                      a section of the file
;;;; on a line of its own                      the file
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

from fpl.ast_surface import Line, Program

type Attachment = Literal["trailing", "doc", "section", "file"]
KINDS: tuple[Attachment, ...] = ("trailing", "doc", "section", "file")


@dataclass(frozen=True)
class Attached:
    """A comment classified: its source line, level, attachment, the source line it attaches to
    (None for a section or the file, or a doc before no code), and its text without marks."""

    line: int
    level: int
    kind: Attachment
    target: int | None
    text: str


def _order(lines: tuple[Line, ...]) -> Iterator[Line]:
    """Lines in the order they are written: each line, then its block."""
    for line in lines:
        yield line
        yield from _order(line.block)


def comments(program: Program) -> tuple[Attached, ...]:
    """Every comment of a program, classified by its level. A string holds none."""
    order = tuple(_order(program.lines))
    found: list[Attached] = []
    for n, line in enumerate(order):
        if line.comment is None:
            continue
        kind = KINDS[min(line.comment.level, len(KINDS)) - 1]
        after = (later.span.line for later in order[n + 1 :] if any(f.cells for f in later.frames))
        target = {"trailing": line.span.line, "doc": next(after, None)}.get(kind)
        text = " ".join(part.lstrip(";⍝").strip() for part in line.comment.lines)
        found.append(Attached(line.comment.span.line, line.comment.level, kind, target, text))
    return tuple(found)
