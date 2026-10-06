"""Every failure the user sees: a position in the source and a message, never a traceback."""

from dataclasses import dataclass
from typing import override


@dataclass(frozen=True)
class Span:
    """Where something is in the source, 1-based, as an editor counts lines and columns."""

    line: int
    col: int


class FplError(Exception):
    """A failure that belongs to the program being run, not to the interpreter."""

    def __init__(self, span: Span, message: str) -> None:
        super().__init__(message)
        self.span = span
        self.message = message

    @override
    def __str__(self) -> str:
        """The one line an `.expected` file holds for an error case (.agents/CONVENTIONS.md)."""
        return f"ERROR: {self.span.line}:{self.span.col} {self.message}"

    def render(self, source: str) -> str:
        """The error line, then the source line it points into with a caret under the column."""
        lines = source.splitlines()
        if not 1 <= self.span.line <= len(lines):
            return str(self)
        text = lines[self.span.line - 1]
        caret = " " * (min(self.span.col, len(text) + 1) - 1) + "^"
        return f"{self}\n{text}\n{caret}"


class FailError(FplError):
    """A miss: no row of a match fits, the +fail a guard counts as not fitting."""
