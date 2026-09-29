"""The instructions of WebAssembly, spec 2.4, for the subset of `fpl.asm.wasm`.

One frozen dataclass per production of the grammar, carrying its number type and operator
(2.4.8 writes `numtype.binop`); operator names are Literal strings, printed as they are. So far:
constants, integer binary operators and return.

A class whose fields are typed by a Literal guards its invariant in `__post_init__`, not with
`icontract.invariant`: CrossHair 0.0.110 cannot build a symbolic Literal and crashes on any
contract that reaches one (HOLES.md, crosshair-literal).
"""

from dataclasses import dataclass
from typing import Literal

from fpl.asm.wasm.types import WIDTH, NumType

IBinop = Literal[
    "add", "sub", "mul", "div_s", "div_u", "rem_s", "rem_u",
    "and", "or", "xor", "shl", "shr_s", "shr_u", "rotl", "rotr",
]  # fmt: skip
"""2.4.8, the integer binary operators."""


def const_in_range(self: "Const") -> bool:
    """A constant is unsigned and fits its type: 0 <= value < 2**N (4.3.1)."""
    return 0 <= self.value < 1 << WIDTH[self.type]


@dataclass(frozen=True, slots=True)
class Const:
    """2.4.8, `t.const c`: the value unsigned, as the abstract syntax holds it.

    Refuses, with ValueError, a value outside 0 <= value < 2**N.
    """

    type: NumType
    value: int

    def __post_init__(self) -> None:
        if not const_in_range(self):
            msg = f"{self.type}.const {self.value} is outside 0 <= value < 2**{WIDTH[self.type]}"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class Binop:
    """2.4.8, `t.binop`: pops two operands of type t, pushes one."""

    type: NumType
    op: IBinop


@dataclass(frozen=True, slots=True)
class Return:
    """2.4.2, `return`: leaves the function with its results."""


Instr = Const | Binop | Return
"""A closed union of the instructions; a match on it is checked for exhaustiveness."""
