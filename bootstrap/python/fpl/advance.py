"""
# Advance

Nagini checks this. It does not call Lark, and it does not override a
dunder.
"""

from dataclasses import dataclass

from nagini_contracts.contracts import Ensures, Requires, Result


@dataclass(frozen=True)
class Span:
    """
    A source position. Nagini sees this. The parser does not live here.
    """

    line: int
    col: int


def column(span: Span) -> int:
    """
    The column, unchanged. The contracts are the whole proof.
    """
    Requires(span.line >= 1)
    Requires(span.col >= 1)
    Ensures(Result() == span.col)
    return span.col
