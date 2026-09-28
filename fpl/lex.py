"""The pre-lexer: what the grammar cannot count, counted before Lark sees the text.

Strings “ ” and 「 」 and block comments ⟦ ⟧ are pairs counted by their own pair only, so they
cannot overlap. A string becomes one placeholder token, its interior left in the source for the
pair's reader; a block comment becomes nothing. Indentation is then held strict: tabs only, and
no bracket left open across a dedent below the line that opened it. The affix pass reads a
token's shape after lexing. Positions stay in the source: every code character keeps its origin.
"""

import re
from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from fpl.ast_surface import Kind
from fpl.errors import FplError, Span

PAIRS = {"“": "”", "「": "」", "⟦": "⟧"}
BRACKETS = {"[": "]", "(": ")", "⟨": "⟩", "{": "}"}
CLOSERS = {close: opener for opener, close in (PAIRS | BRACKETS).items()}
PLACEHOLDER = "¶"
SPECIAL = re.compile(r"[“「⟦”」⟧;⍝]")
LINE_COMMENT = re.compile(r"(;+|⍝)[^\n]*")
MODS = "\u00b4`\u00a8\u02dc\u207c\u02d9"
SHAPE = re.compile(rf"(->|→|\$|#|&|\.\./|\.\.)?([^{MODS}]*?)([{MODS}]*)")
NUMBER = re.compile(r"-?(\d+(\.\d+)?|∞|π)")


class Lines:
    """Offsets into a source as the 1-based line and column an editor shows."""

    def __init__(self, source: str) -> None:
        self.starts = [0] + [n + 1 for n, char in enumerate(source) if char == "\n"]

    def span(self, offset: int) -> Span:
        """The line and column of a source offset; the end is just past the last line."""
        line = bisect_right(self.starts, offset)
        return Span(line, offset - self.starts[line - 1] + 1)


@dataclass(frozen=True)
class Stashed:
    """A string's interior, [start, end) in the source: `str` interpolates ⟨ ⟩, `raw` does not.
    depth is the tabs before the line it opens on, which its continuation lines drop (S26)."""

    kind: Literal["str", "raw"]
    start: int
    end: int
    depth: int


@dataclass(frozen=True)
class Prelexed:
    """Code for the grammar, the source offset of each of its characters and of its end, and the
    string each placeholder stands for, by the placeholder's offset in the code."""

    code: str
    origin: tuple[int, ...]
    stash: dict[int, Stashed]


def counted(text: str, at: int, close: str, end: int) -> int:
    """The offset just past the closer that balances the opener at `at`, or -1 if none does
    before `end`. Only the opener's own pair is counted."""
    opener, depth, j = text[at], 1, at + 1
    while j < end and depth:
        depth += (text[j] == opener) - (text[j] == close)
        j += 1
    return -1 if depth else j


class _Code:
    """The code being written, each character with its source offset."""

    def __init__(self) -> None:
        self.chars: list[str] = []
        self.origin: list[int] = []
        self.stash: dict[int, Stashed] = {}

    def put(self, text: str, at: int, verbatim: bool = True) -> None:
        """Append text from source offset `at`; a pad or placeholder keeps `at` for every char."""
        self.chars.extend(text)
        self.origin.extend(at + k if verbatim else at for k in range(len(text)))

    def at_line_start(self) -> bool:
        """Nothing but tabs written since the last newline."""
        for char in reversed(self.chars):
            if char != "\t":
                return char == "\n"
        return True


def _pair(source: str, at: int, end: int, code: _Code) -> int:
    """Write the string or comment opening at `at`; return the offset after its closer."""
    opener = source[at]
    after = counted(source, at, PAIRS[opener], end)
    if after < 0:
        raise FplError(Lines(source).span(at), f"{opener} never closed")
    if opener == "⟦":
        if code.at_line_start():
            return len(source[after:end]) - len(source[after:end].lstrip(" ")) + after
        code.put(" ", at, verbatim=False)
        return after
    if code.chars and code.chars[-1] not in " \t\n":
        code.put(" ", at, verbatim=False)
    line = source.rfind("\n", 0, at) + 1
    depth = len(source[line:at]) - len(source[line:at].lstrip("\t"))
    code.stash[len(code.chars)] = Stashed(
        "str" if opener == "“" else "raw", at + 1, after - 1, depth
    )
    code.put(PLACEHOLDER + " ", at, verbatim=False)
    return after


def _special(source: str, at: int, end: int, code: _Code) -> int:
    """Write what starts with a special character at `at`; return where the next write starts."""
    char = source[at]
    if char in PAIRS:
        return _pair(source, at, end, code)
    if char in CLOSERS:
        raise FplError(Lines(source).span(at), f"{char} closes nothing")
    newline = source.find("\n", at, end)
    after = end if newline < 0 else newline
    code.put(source[at:after], at)
    return after


def pairs(
    source: str, start: int = 0, end: int | None = None, special: re.Pattern[str] = SPECIAL
) -> Prelexed:
    """Stash the strings and drop the block comments of source[start:end], ending the code in a
    newline; `special` names the characters that open or close a pair or a line comment. Refuses
    a pair never closed and a closer with no opener; indentation is not looked at."""
    stop = len(source) if end is None else end
    code, at = _Code(), start
    while at < stop:
        found = special.search(source, at, stop)
        upto = found.start() if found else stop
        code.put(source[at:upto], at)
        at = _special(source, upto, stop, code) if found else stop
    code.put("\n", stop, verbatim=False)
    return Prelexed("".join(code.chars), (*code.origin, stop), code.stash)


def prelex(source: str, start: int = 0, end: int | None = None) -> Prelexed:
    """Pre-lex source[start:end] (all of it by default) to code the grammar reads, ending in a
    newline. Refuses a pair never closed, a closer with no opener, and loose indentation."""
    lexed = pairs(source, start, end)
    strict(source, lexed.code, lexed.origin)
    return lexed


class _RefusalError(Exception):
    """A strictness refusal at a code offset, before it is placed in the source."""

    def __init__(self, offset: int, message: str) -> None:
        super().__init__(message)
        self.offset = offset
        self.message = message


def _brackets(line: str, base: int, depth: int, open_: list[tuple[str, int, int]]) -> None:
    """Track the brackets of one code line, its line comment aside, on the stack of open ones;
    refuse a closer that closes nothing or not the latest opener. Offsets are into the code."""
    body = LINE_COMMENT.split(line, maxsplit=1)[0]
    for n, char in enumerate(body):
        if char in BRACKETS:
            open_.append((char, base + n, depth))
        elif char in CLOSERS and not open_:
            raise _RefusalError(base + n, f"{char} closes nothing")
        elif char in CLOSERS and open_[-1][0] != CLOSERS[char]:
            raise _RefusalError(base + n, f"{char} does not close {open_[-1][0]}")
        elif char in CLOSERS:
            open_.pop()


def _lines(code: str, line_of: Callable[[int], int]) -> None:
    """Refuse leading spaces outside brackets, and a dedent below the line of a bracket still
    open; the dedent is reported at the dedenting line and names the opener's line."""
    open_: list[tuple[str, int, int]] = []
    base = 0
    for line in code.split("\n"):
        depth = len(line) - len(line.lstrip("\t"))
        if not open_ and line[depth : depth + 1] == " ":
            raise _RefusalError(base + depth, "indentation must be tabs")
        if open_ and line.strip() and depth < open_[-1][2]:
            opener, opened, _ = open_[-1]
            message = f"dedent below line {line_of(opened)}, but its {opener} is still open"
            raise _RefusalError(base + depth, message)
        _brackets(line, base, depth, open_)
        base += len(line) + 1
    if open_:
        raise _RefusalError(open_[-1][1], f"{open_[-1][0]} never closed")


def strict(source: str, code: str, origin: tuple[int, ...]) -> None:
    """Hold the code to strict indentation, reporting a refusal at its place in the source."""
    lines = Lines(source)
    try:
        _lines(code, lambda offset: lines.span(origin[offset]).line)
    except _RefusalError as refusal:
        raise FplError(lines.span(origin[refusal.offset]), refusal.message) from None


def shape(token: str) -> tuple[str, Kind, tuple[str, ...], str] | None:
    """A token's prefix sigil, kind, body (a path's segments) and suffix modifiers, or None
    when a modifier stands anywhere but at the end."""
    match = SHAPE.fullmatch(token)
    if match is None:
        return None
    prefix, body, mods = match.group(1) or "", match.group(2), match.group(3)
    kind: Kind = (
        "modifier"
        if not body
        else "number"
        if NUMBER.fullmatch(body)
        else "path"
        if "/" in body
        else "name"
    )
    return prefix, kind, tuple(body.split("/")) if kind == "path" else (body,), mods
