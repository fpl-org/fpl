"""Source text to the surface AST: pre-lex, the tab indenter, LALR over fpl/grammar.lark, then
the affix pass on every token. No semantics live here (docs/CONVENTIONS.md)."""

from collections.abc import Callable, Iterator
from functools import cache
from pathlib import Path
from typing import override

import icontract
from lark import Lark, Token, Tree, UnexpectedInput
from lark.indenter import DedentError, Indenter

from fpl.ast_surface import Cell, Enclosure, Frame, Item, Line, Pair, Program, Text, Word
from fpl.errors import FplError, Span
from fpl.lex import BRACKETS, Lines, Prelexed, Stashed, counted, prelex, shape

GRAMMAR = Path(__file__).with_name("grammar.lark")
PAIRS: dict[str, Pair] = {
    "quotation": "quotation",
    "prefix": "prefix",
    "group": "group",
    "dict": "dict",
}


class MisindentedError(Exception):
    """The indenter met a dedent to a level no line opened, at the newline token given."""

    def __init__(self, token: Token) -> None:
        super().__init__(token)
        self.token = token


class FplIndenter(Indenter):
    """One tab per level; a newline inside [ ] ( ) ⟨ ⟩ { } is not block structure."""

    NL_type = "_NL"  # pyright: ignore[reportIncompatibleMethodOverride, reportAssignmentType] -- lark declares an abstract property and reads a class attribute
    OPEN_PAREN_types = ["LSQB", "LPAR", "_LANGLE", "_LBRACE"]  # noqa: RUF012 -- lark reads a class attribute  # pyright: ignore[reportIncompatibleMethodOverride, reportAssignmentType] -- lark declares an abstract property and reads a class attribute
    CLOSE_PAREN_types = ["RSQB", "RPAR", "_RANGLE", "_RBRACE"]  # noqa: RUF012 -- lark reads a class attribute  # pyright: ignore[reportIncompatibleMethodOverride, reportAssignmentType] -- lark declares an abstract property and reads a class attribute
    INDENT_type = "_INDENT"  # pyright: ignore[reportIncompatibleMethodOverride, reportAssignmentType] -- lark declares an abstract property and reads a class attribute
    DEDENT_type = "_DEDENT"  # pyright: ignore[reportIncompatibleMethodOverride, reportAssignmentType] -- lark declares an abstract property and reads a class attribute
    tab_len = 1  # pyright: ignore[reportIncompatibleMethodOverride, reportAssignmentType] -- lark declares an abstract property and reads a class attribute

    @override
    def handle_NL(self, token: Token) -> Iterator[Token]:
        """Lark's indentation, with the newline where a dedent went wrong kept for the error."""
        try:
            yield from super().handle_NL(token)
        except DedentError as failure:
            raise MisindentedError(token) from failure


@cache
def parser() -> Lark:
    """The LALR parser, fed by the tab indenter."""
    return Lark(
        GRAMMAR.read_text(),
        parser="lalr",
        postlex=FplIndenter(),
        propagate_positions=True,
        maybe_placeholders=False,
    )


def parse(source: str) -> Program:
    """Parse source text to the surface AST. Every refusal, the pre-lexer's, the indenter's or
    the grammar's, is an FplError at a position inside the source; nothing else escapes.
    Nesting deeper than the build can recurse to is refused at the source's start."""
    try:
        return read(source, Lines(source), 0, len(source))
    except RecursionError:
        raise FplError(Span(1, 1), "nesting too deep to read") from None


def read(source: str, lines: Lines, start: int, end: int) -> Program:
    """Parse source[start:end], placing every node in the whole source."""
    lexed = prelex(source, start, end)
    tree = _tree(source, lexed)
    return _Build(source, lines, lexed).program(tree, lines.span(start))


def _tree(source: str, lexed: Prelexed) -> Tree[Token]:
    """Lark's tree for the pre-lexed code, or its failure placed in the source."""
    try:
        return parser().parse(lexed.code)  # pyright: ignore[reportUnknownMemberType] -- lark types its text argument loosely
    except UnexpectedInput as failure:
        raise FplError(placed(source, lexed, failure.pos_in_stream), "unexpected input") from None
    except MisindentedError as failure:
        where_ = placed(source, lexed, failure.token.end_pos)
        raise FplError(where_, "dedent to a level never opened") from None


def placed(source: str, lexed: Prelexed, offset: int | None) -> Span:
    """The source position of a code offset; Lark's unknown or end position is the source's end."""
    if offset is None or offset < 0:
        return where(source, -1, -1)
    at = Lines(source).span(lexed.origin[offset])
    return where(source, at.line, at.col)


class _Build:
    """The surface AST from Lark's tree, every node placed through the code's origins."""

    def __init__(self, source: str, lines: Lines, lexed: Prelexed) -> None:
        self.source, self.lines, self.lexed = source, lines, lexed

    def at(self, tree: Tree[Token], outer: Span) -> Span:
        """Where a subtree starts, or `outer` for one that matched nothing."""
        if tree.meta.empty:
            return outer
        return self.lines.span(self.lexed.origin[tree.meta.start_pos])

    def program(self, tree: Tree[Token], outer: Span) -> Program:
        """The start rule: the program's lines."""
        return Program(self.subtrees(tree, outer, self.line), outer)

    def subtrees[T](
        self, tree: Tree[Token], outer: Span, build: Callable[[Tree[Token], Span], T]
    ) -> tuple[T, ...]:
        """Each child subtree built."""
        return tuple(build(child, outer) for child in tree.children if isinstance(child, Tree))

    def line(self, tree: Tree[Token], outer: Span) -> Line:
        """frames _NL block?"""
        span = self.at(tree, outer)
        frames, *block = tree.children
        assert isinstance(frames, Tree)
        lines = tuple(
            line
            for child in block
            if isinstance(child, Tree)
            for line in self.subtrees(child, span, self.line)
        )
        return Line(self.subtrees(frames, span, self.frame), lines, span)

    def frames(self, tree: Tree[Token], outer: Span) -> tuple[Frame, ...]:
        """frame (_BAR frame)*"""
        return self.subtrees(tree, outer, self.frame)

    def frame(self, tree: Tree[Token], outer: Span) -> Frame:
        """_TABS? (cell (_TABS cell)* _TABS?)?"""
        span = self.at(tree, outer)
        return Frame(self.subtrees(tree, span, self.cell), span)

    def cell(self, tree: Tree[Token], outer: Span) -> Cell:
        """item+"""
        span = self.at(tree, outer)
        return Cell(tuple(self.item(child, span) for child in tree.children), span)

    def item(self, child: Tree[Token] | Token, outer: Span) -> Item:
        """A token, a string placeholder, or an enclosure."""
        if isinstance(child, Tree):
            span = self.at(child, outer)
            inside = tuple(
                frame for sub in self.subtrees(child, span, self.frames) for frame in sub
            )
            return Enclosure(PAIRS[str(child.data)], inside, span)
        start = child.start_pos or 0
        span = self.lines.span(self.lexed.origin[start])
        stashed = self.lexed.stash.get(start)
        if stashed is not None:
            return self.text(stashed, span)
        return self.word(str(child), span)

    def word(self, token: str, span: Span) -> Word:
        """The affix pass on one token."""
        read_ = shape(token)
        if read_ is None:
            raise FplError(span, f"a modifier ends its word: {token}")
        prefix, kind, body, mods = read_
        return Word(prefix, kind, body, mods, span)

    def text(self, stashed: Stashed, span: Span) -> Text:
        """A string's interior: a raw one whole; an interpolating one split into text, with the
        incidental indentation of its continuation lines dropped (S26), and ⟨ ⟩ islands read."""
        if stashed.kind == "raw":
            return Text("raw", (self.source[stashed.start : stashed.end],), span)
        parts: list[str | Program] = []
        at = stashed.start
        while at < stashed.end:
            island = self.source.find("⟨", at, stashed.end)
            upto = stashed.end if island < 0 else island
            if upto > at:
                parts.append(self.source[at:upto].replace("\n" + "\t" * stashed.depth, "\n"))
            at = upto if island < 0 else self.island(island, stashed.end, parts)
        return Text("str", tuple(parts), span)

    def island(self, at: int, end: int, parts: list[str | Program]) -> int:
        """Read the ⟨ ⟩ island opening at `at` into parts; return the offset after it."""
        after = counted(self.source, at, BRACKETS["⟨"], end)
        if after < 0:
            raise FplError(self.lines.span(at), "⟨ never closed")
        parts.append(read(self.source, self.lines, at + 1, after - 1))
        return after


def within(source: str, line: int, col: int) -> bool:
    """Line and column name a character of the source, or the position just past a line."""
    lines = source.split("\n")
    return 1 <= line <= len(lines) and 1 <= col <= len(lines[line - 1]) + 1


def reported(source: str, line: int, column: int) -> bool:
    """What Lark reports for a failure: a position within the source, or line -1 for its end."""
    return line == -1 or within(source, line, column)


def inside(result: Span, source: str) -> bool:
    """The position given is within the source."""
    return within(source, result.line, result.col)


@icontract.require(reported)
@icontract.ensure(inside)
def where(source: str, line: int, column: int) -> Span:
    """The position of a parse failure. Lark gives -1 for the end of the input; that is the
    position just after the last character."""
    if line >= 1:
        return Span(line, column)
    lines = source.split("\n")
    return Span(len(lines), len(lines[-1]) + 1)
