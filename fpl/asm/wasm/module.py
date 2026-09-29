"""The module of WebAssembly, spec 2.5, for the subset of `fpl.asm.wasm`.

A module's fields are tuples in the field order of 2.5, indexed from 0 in each index space, which
imports open. Of the subset's limits, one belongs to the module as a whole: at most one memory,
counting imports; `Module` refuses a second with ValueError, so such a module never exists.
"""

from dataclasses import dataclass
from typing import Literal

from fpl.asm.wasm.instr import Instr
from fpl.asm.wasm.types import FuncType, GlobalType, MemType, TableType, ValType

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
class Global:
    """2.5.4: a global of `type`, initialised by the constant expression `init`."""

    type: GlobalType
    init: Expr


@dataclass(frozen=True, slots=True)
class Mem:
    """2.5.5: a memory."""

    type: MemType


@dataclass(frozen=True, slots=True)
class Table:
    """2.5.6: a table of (ref null func), every element null until an element segment fills it."""

    type: TableType


@dataclass(frozen=True, slots=True)
class Data:
    """2.5.8: an active data segment, copying `init` into memory 0 at `offset` on instantiation."""

    offset: Expr
    init: bytes


@dataclass(frozen=True, slots=True)
class Elem:
    """2.5.9: an active funcref segment, putting `funcs` into `table` at `offset`.

    The abstract syntax holds `(ref.func x)` expressions; the subset holds just the indices x.
    """

    table: int
    offset: Expr
    funcs: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class FuncImport:
    """2.5.11, an imported function of type index `type`."""

    type: int


@dataclass(frozen=True, slots=True)
class TableImport:
    """2.5.11, an imported table."""

    type: TableType


@dataclass(frozen=True, slots=True)
class MemImport:
    """2.5.11, an imported memory."""

    type: MemType


@dataclass(frozen=True, slots=True)
class GlobalImport:
    """2.5.11, an imported global."""

    type: GlobalType


ImportDesc = FuncImport | TableImport | MemImport | GlobalImport
"""2.5.11, what an import brings in, and the index space it opens."""


@dataclass(frozen=True, slots=True)
class Import:
    """2.5.11: imports `desc` as `name` from `module`."""

    module: str
    name: str
    desc: ImportDesc


def one_memory(self: "Module") -> bool:
    """At most one memory, counting imported ones: the subset's memory index is 0 only."""
    imported = sum(isinstance(i.desc, MemImport) for i in self.imports)
    return imported + len(self.mems) <= 1


@dataclass(frozen=True, slots=True)
class Module:
    """2.5: a module's fields, each a tuple in the order of its index space; `start` optional.

    Refuses, with ValueError, a second memory (HOLES.md crosshair-literal: `Export.kind` is a
    Literal, so this guard is `__post_init__`, not `icontract.invariant`).
    """

    types: tuple[FuncType, ...] = ()
    imports: tuple[Import, ...] = ()
    globals: tuple[Global, ...] = ()
    mems: tuple[Mem, ...] = ()
    tables: tuple[Table, ...] = ()
    funcs: tuple[Func, ...] = ()
    datas: tuple[Data, ...] = ()
    elems: tuple[Elem, ...] = ()
    start: int | None = None
    exports: tuple[Export, ...] = ()

    def __post_init__(self) -> None:
        if not one_memory(self):
            msg = "a module holds at most one memory, counting imports"
            raise ValueError(msg)
