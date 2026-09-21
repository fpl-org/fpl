"""Source text to a Lark tree. No semantics live here (docs/CONVENTIONS.md)."""

from functools import cache
from pathlib import Path

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
        raise FplError(where(source, failure), "unexpected input") from failure


def where(source: str, failure: UnexpectedInput) -> Span:
    """The position of a parse failure. Lark gives -1 for the end of the input; that is the
    position just after the last character."""
    if failure.line >= 1:
        return Span(failure.line, failure.column)
    lines = source.split("\n")
    return Span(len(lines), len(lines[-1]) + 1)
