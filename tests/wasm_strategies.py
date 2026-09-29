"""Hypothesis strategies for fpl.asm.wasm: the numbers and modules the properties draw.

The structural strategy (`INSTRS`, `FIELDS`, `module_parts`, `module_of`) builds every class
of the model over drawn fields: total and untyped, it draws modules the printer must print
but no validator need accept. `INSTRS` maps each `Instr` class to its builder and `FIELDS`
each `Module` field to its strategy, so a test can compare their keys with the model's.
"""

import contextlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from itertools import product
from typing import Any, get_args

from hypothesis import strategies as st

from fpl.asm.wasm.instr import (
    Binop,
    Block,
    Br,
    BrIf,
    BrTable,
    Call,
    CallIndirect,
    Const,
    Cvtop,
    Drop,
    GlobalGet,
    GlobalSet,
    IBinop,
    ICvtop,
    If,
    Instr,
    IRelop,
    ITestop,
    IUnop,
    Load,
    LocalGet,
    LocalSet,
    LocalTee,
    Loop,
    MemArg,
    MemorySize,
    Nop,
    PackSize,
    Relop,
    Return,
    ReturnCall,
    ReturnCallIndirect,
    Select,
    Sign,
    Store,
    Testop,
    Unop,
    Unreachable,
)
from fpl.asm.wasm.module import (
    Data,
    Elem,
    Export,
    ExternKind,
    Func,
    FuncImport,
    Global,
    GlobalImport,
    Import,
    ImportDesc,
    Mem,
    MemImport,
    Module,
    Table,
    TableImport,
)
from fpl.asm.wasm.types import (
    WIDTH,
    FuncType,
    GlobalType,
    Limits,
    MemType,
    NumType,
    TableType,
    TypeUse,
)

numtypes = st.sampled_from(get_args(NumType))
valtypes = st.lists(numtypes, max_size=3).map(tuple)


def operands(t: NumType) -> st.SearchStrategy[int]:
    """Values of type t, biased to 0, 1, -1, the signed extremes and shift counts at N."""
    n = WIDTH[t]
    edges = [0, 1, 2**n - 1, 2 ** (n - 1), 2 ** (n - 1) - 1, n, n + 1]
    return st.sampled_from(edges) | st.integers(min_value=0, max_value=2**n - 1)


@dataclass(frozen=True)
class BinopMain:
    """An exported function returning `a op b` in type t; its params and locals go unused."""

    type: NumType
    op: IBinop
    a: int
    b: int
    params: tuple[NumType, ...] = ()
    locals: tuple[NumType, ...] = ()
    name: str = "main"

    def module(self) -> Module:
        """The module holding just that function and its export."""
        t = self.type
        body = (Const(t, self.a), Const(t, self.b), Binop(t, self.op), Return())
        return Module(
            types=(FuncType(self.params, (t,)),),
            funcs=(Func(0, self.locals, body),),
            exports=(Export(self.name, "func", 0),),
        )


@st.composite
def binop_mains(draw: st.DrawFn, *, unused: bool = False) -> BinopMain:
    """A BinopMain; with `unused`, also drawn params, locals and export name."""
    t = draw(numtypes)
    op = draw(st.sampled_from(get_args(IBinop)))
    case = BinopMain(t, op, draw(operands(t)), draw(operands(t)))
    if not unused:
        return case
    return BinopMain(t, op, case.a, case.b, draw(valtypes), draw(valtypes), draw(st.text()))


def _legal[T](build: Callable[..., T], *domains: Iterable[object]) -> tuple[T, ...]:
    """Every value `build` accepts over the product of `domains`, in product order: the
    class's own guard, raising ValueError, decides what is legal, not a copy of it here."""
    legal: list[T] = []
    for args in product(*domains):
        with contextlib.suppress(ValueError):
            legal.append(build(*args))
    return tuple(legal)


NUMTYPES: tuple[NumType, ...] = get_args(NumType)
UNOPS = _legal(Unop, NUMTYPES, get_args(IUnop))
BINOPS = _legal(Binop, NUMTYPES, get_args(IBinop))
TESTOPS = _legal(Testop, NUMTYPES, get_args(ITestop))
RELOPS = _legal(Relop, NUMTYPES, get_args(IRelop))
CVTOPS = _legal(Cvtop, NUMTYPES, get_args(ICvtop), NUMTYPES)
PACKS = (None, *product(get_args(PackSize), get_args(Sign)))
LOADS = _legal(Load, NUMTYPES, (MemArg(0, 0),), PACKS)
STORES = _legal(Store, NUMTYPES, (MemArg(0, 0),), (None, *get_args(PackSize)))
EXTERN_KINDS: tuple[ExternKind, ...] = get_args(ExternKind)
"""The legal instances of each finite-operator class, and the export kinds, enumerated."""

u32s = st.integers(min_value=0, max_value=2**32 - 1)
typeuses = st.builds(TypeUse, u32s)
blocktypes = st.none() | numtypes | typeuses
memargs = st.builds(MemArg, st.integers(min_value=0, max_value=8), u32s)
"""Alignment exponents stop at 8: the printer writes `align=2**a`, and the model's bound of
2**32 would print a number of 2**32 bits."""


def _rearg[M: (Load, Store)](instr: M, arg: MemArg) -> M:
    """`instr` accessing memory through `arg` instead."""
    return replace(instr, arg=arg)


instrs: st.SearchStrategy[Instr] = st.deferred(lambda: st.one_of(*INSTRS.values()))
exprs = st.lists(instrs, max_size=3).map(tuple)

INSTRS: dict[type[Instr], st.SearchStrategy[Instr]] = {
    Const: numtypes.flatmap(lambda t: st.builds(Const, st.just(t), operands(t))),
    Unop: st.sampled_from(UNOPS),
    Binop: st.sampled_from(BINOPS),
    Testop: st.sampled_from(TESTOPS),
    Relop: st.sampled_from(RELOPS),
    Cvtop: st.sampled_from(CVTOPS),
    Load: st.builds(_rearg, st.sampled_from(LOADS), memargs),
    Store: st.builds(_rearg, st.sampled_from(STORES), memargs),
    Select: st.builds(Select, st.none() | valtypes),
    BrTable: st.builds(BrTable, st.lists(u32s, max_size=3).map(tuple), u32s),
    Block: st.builds(Block, blocktypes, exprs),
    Loop: st.builds(Loop, blocktypes, exprs),
    If: st.builds(If, blocktypes, exprs, exprs),
    **{cls: st.builds(cls, u32s, typeuses) for cls in (CallIndirect, ReturnCallIndirect)},
    **{cls: st.builds(cls) for cls in (Nop, Unreachable, Drop, Return, MemorySize)},
    **{
        cls: st.builds(cls, u32s)
        for cls in (LocalGet, LocalSet, LocalTee, GlobalGet, GlobalSet, Br, BrIf, Call, ReturnCall)
    },
}
"""The builder of each instruction class; nested bodies hold up to three instructions."""

limits = st.builds(Limits, u32s, st.none() | u32s)
tabletypes = st.builds(TableType, limits)
memtypes = st.builds(MemType, limits)
globaltypes = st.builds(GlobalType, st.booleans(), numtypes)

DESCS: dict[type[ImportDesc], st.SearchStrategy[ImportDesc]] = {
    FuncImport: st.builds(FuncImport, u32s),
    TableImport: st.builds(TableImport, tabletypes),
    MemImport: st.builds(MemImport, memtypes),
    GlobalImport: st.builds(GlobalImport, globaltypes),
}
"""The builder of each import description kind."""


def _tuples[T](of: st.SearchStrategy[T], max_size: int = 3) -> st.SearchStrategy[tuple[T, ...]]:
    """Tuples of up to `max_size` elements drawn from `of`."""
    return st.lists(of, max_size=max_size).map(tuple)


FIELDS: dict[str, st.SearchStrategy[Any]] = {
    "types": _tuples(st.builds(FuncType, valtypes, valtypes)),
    "imports": _tuples(st.builds(Import, st.text(), st.text(), st.one_of(*DESCS.values()))),
    "globals": _tuples(st.builds(Global, globaltypes, exprs)),
    "mems": _tuples(st.builds(Mem, memtypes), max_size=1),
    "tables": _tuples(st.builds(Table, tabletypes)),
    "funcs": _tuples(st.builds(Func, u32s, valtypes, exprs)),
    "datas": _tuples(st.builds(Data, exprs, st.binary())),
    "elems": _tuples(st.builds(Elem, u32s, exprs, _tuples(u32s))),
    "start": st.none() | u32s,
    "exports": _tuples(st.builds(Export, st.text(), st.sampled_from(EXTERN_KINDS), u32s)),
}
"""The strategy of each `Module` field, untyped: indices need not point anywhere."""

module_parts = st.fixed_dictionaries(FIELDS)


def module_of(parts: dict[str, Any]) -> Module:
    """The module of drawn `parts`, keeping its first memory (a defined one before an imported
    one) and dropping every later memory import, since `Module` refuses a second memory."""
    memories = len(parts["mems"])
    kept: list[Import] = []
    for imported in parts["imports"]:
        is_memory = isinstance(imported.desc, MemImport)
        memories += is_memory
        if not is_memory or memories == 1:
            kept.append(imported)
    kept_parts: dict[str, Any] = {**parts, "imports": tuple(kept)}
    return Module(**kept_parts)
