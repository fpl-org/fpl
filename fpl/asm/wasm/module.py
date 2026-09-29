"""The module of WebAssembly, spec 2.5, for the subset of `fpl.asm.wasm`.

A module's fields are tuples in the field order of 2.5, indexed from 0 in each index space.
So far: types, functions and exports.
"""

from dataclasses import dataclass
from typing import Literal

from fpl.asm.wasm.instr import Instr
from fpl.asm.wasm.types import FuncType, ValType

Expr = tuple[Instr, ...]
"""2.4.10, an expression: a sequence of instructions (the closing `end` is implicit)."""

ExternKind = Literal["func", "table", "memory", "global"]
"""2.5.12, what an export exports."""


@dataclass(frozen=True, slots=True)
class Func:
    """2.5.7: a function, by its type's index, with its declared locals and its body."""

    type: int
    locals: tuple[ValType, ...]
    body: Expr


@dataclass(frozen=True, slots=True)
class Export:
    """2.5.12: exports the `kind` at `index` under `name`."""

    name: str
    kind: ExternKind
    index: int


@dataclass(frozen=True, slots=True)
class Module:
    """2.5: a module's fields, each a tuple in the order of its index space."""

    types: tuple[FuncType, ...] = ()
    funcs: tuple[Func, ...] = ()
    exports: tuple[Export, ...] = ()
