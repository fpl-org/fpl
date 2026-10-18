"""
# Pass

Python has no pipe operator. `>>` on a Pass is composition. On an int it
stays a shift.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Pass[A, B]:
    """
    One arrow. Calling it runs the function. >> builds the next arrow.
    """

    name: str
    fn: Callable[[A], B]

    def __call__(self, value: A) -> B:
        return self.fn(value)

    def __rshift__[C](self, nxt: Pass[B, C]) -> Pass[A, C]:
        return Pass(f"{self.name}>>{nxt.name}", lambda value: nxt(self(value)))
