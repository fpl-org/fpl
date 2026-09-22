"""Source text to a Lark tree. No semantics live here (docs/CONVENTIONS.md)."""

from functools import cache
from pathlib import Path

import icontract
from lark import Lark, Token, Tree, UnexpectedInput

from fpl.errors import FplError, Span

GRAMMAR = Path(__file__).with_name("grammar.lark")


@cache
def parser(grammar: Path = GRAMMAR) -> Lark:
    """The Earley parser for a grammar file, with ambiguity kept explicit (docs/STACK.md)."""
    if not grammar.is_file():
        raise FplError(Span(1, 1), f"no grammar yet: {grammar.name} is the maintainer's to write")
    return Lark(
        grammar.read_text(), parser="earley", ambiguity="explicit", propagate_positions=True
    )


def parse(source: str, grammar: Path = GRAMMAR) -> Tree[Token]:
    """Parse source text, turning Lark's failure into an FplError at the offending position."""
    try:
        return parser(grammar).parse(source)  # pyright: ignore[reportUnknownMemberType] -- lark types its text argument loosely
    except UnexpectedInput as failure:
        raise FplError(where(source, failure.line, failure.column), "unexpected input") from failure


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
