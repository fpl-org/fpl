"""The types of WebAssembly, spec 2.3, restricted to the subset of `fpl.asm.wasm`.

Number types are i32 and i64 only; value types are number types (no vectors, no references
on the operand stack); a defined type is a function type, standing for a singleton, final,
non-recursive recursive type (2.5.2); memories and tables have address type i32, and a table's
element type is (ref null func). Every type is a frozen value: equality is structural.
"""

from dataclasses import dataclass
from typing import Literal

NumType = Literal["i32", "i64"]
"""2.3.1, the integer number types."""

ValType = NumType
"""2.3.6: no vector types, no reference types on the operand stack."""

WIDTH: dict[NumType, int] = {"i32": 32, "i64": 64}
"""The bit width |t| of a number type (2.3.1), the N of the integer operators (4.3.2)."""


@dataclass(frozen=True, slots=True)
class FuncType:
    """2.3.9: a function type, parameters to results."""

    params: tuple[ValType, ...]
    results: tuple[ValType, ...]


@dataclass(frozen=True, slots=True)
class Limits:
    """2.3.12: the minimum and optional maximum size of a memory (in pages) or table."""

    min: int
    max: int | None


@dataclass(frozen=True, slots=True)
class MemType:
    """2.3.15: a memory type, address type i32, page size 64 KiB."""

    limits: Limits


@dataclass(frozen=True, slots=True)
class TableType:
    """2.3.16: a table type, address type i32, element type (ref null func)."""

    limits: Limits


@dataclass(frozen=True, slots=True)
class GlobalType:
    """2.3.14: a global's value type and whether it is mutable."""

    mutable: bool
    type: ValType


@dataclass(frozen=True, slots=True)
class TypeUse:
    """2.3.3: a type index, as a block type or an indirect call names it."""

    index: int


BlockType = ValType | TypeUse | None
"""2.3.8: no result, one value type, or a type index."""
