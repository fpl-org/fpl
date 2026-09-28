"""Comments as trivia beside the AST: the ; level is the attachment (S33).

;    after code on its line     the line it ends (trailing)
;;   on its own line            the next code line (before); above or first under a head, its doc
;;;  own line, column 0         a section of the file
;;;; own line, column 0         the file
"""

import re
from dataclasses import dataclass
from typing import Literal

from fpl.lex import Lines, prelex

type Attachment = Literal["trailing", "before", "doc", "section", "file"]
HEAD = re.compile(r"\t*\S+\s*:\s")
LEVEL = re.compile(r";+")


@dataclass(frozen=True)
class Comment:
    """A ; comment: its source line, level, attachment, the source line it attaches to (None for
    a section or the file, or before nothing), and its text."""

    line: int
    level: int
    kind: Attachment
    target: int | None
    text: str


def _code(line: str) -> bool:
    """A line with code on it."""
    return bool(line.strip()) and not line.lstrip().startswith(";")


def _depth(line: str) -> int:
    """The tabs a line is indented by."""
    return len(line) - len(line.lstrip("\t"))


def _code_line(lines: list[str], indices: range) -> int | None:
    """The first code line among the indices, in their order."""
    return next((n for n in indices if _code(lines[n])), None)


def _head(lines: list[str], k: int | None) -> int | None:
    """Line k when it is a code line that opens a definition (name: ...)."""
    return k if k is not None and HEAD.match(lines[k]) else None


def _own_line(lines: list[str], k: int, level: int) -> tuple[Attachment, int | None]:
    """What a comment alone on code line k attaches to, as a code line index."""
    depth = _depth(lines[k])
    if depth == 0 and level >= 3:
        return ("file" if level >= 4 else "section"), None
    after = _code_line(lines, range(k + 1, len(lines)))
    if _head(lines, after) is not None:
        return "doc", after
    above = _head(lines, _code_line(lines, range(k - 1, -1, -1)))
    if above is not None and depth > _depth(lines[above]):
        return "doc", above
    return "before", after


def comments(source: str) -> tuple[Comment, ...]:
    """Every ; comment of a source that pre-lexes, classified. Strings are not searched."""
    lexed, lines = prelex(source), Lines(source)
    code = lexed.code.split("\n")
    starts = [0]
    for line in code:
        starts.append(starts[-1] + len(line) + 1)

    def at(k: int | None) -> int | None:
        return None if k is None else lines.span(lexed.origin[starts[k]]).line

    found: list[Comment] = []
    for k, line in enumerate(code):
        level = LEVEL.search(line)
        if level is None:
            continue
        text = line[level.end() :].strip()
        size = len(level.group())
        if line[: level.start()].strip():
            found.append(Comment(at(k) or 0, size, "trailing", at(k), text))
            continue
        kind, target = _own_line(code, k, size)
        found.append(Comment(at(k) or 0, size, kind, at(target), text))
    return tuple(found)
