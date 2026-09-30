"""Hypothesis strategies for fpl.asm.wasm: the numbers and modules the properties draw.

The structural strategy (`INSTRS`, `FIELDS`, `module_parts`, `module_of`) builds every class
of the model over drawn fields: total and untyped, it draws modules the printer must print
but no validator need accept. `INSTRS` maps each `Instr` class to its builder and `FIELDS`
each `Module` field to its strategy, so a test can compare their keys with the model's.

The valid strategy (`valid_modules`) is typed by construction (design section 7): it draws a
module's context first (types with deliberate duplicates, imports unless `closed`, globals, at
most one memory, tables, function signatures), then each body against it, so every module it
draws is one every validator must accept.
"""

import contextlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from itertools import product
from typing import Any, assert_never, get_args

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
    BlockType,
    FuncType,
    GlobalType,
    Limits,
    MemType,
    NumType,
    TableType,
    TypeUse,
    ValType,
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


small_limits = st.integers(min_value=0, max_value=2).flatmap(
    lambda low: st.builds(Limits, st.just(low), st.none() | st.integers(low, low + 2))
)
"""Limits of a few pages or elements, the maximum absent or at least the minimum (3.2.12)."""
small_tabletypes = st.builds(TableType, small_limits)
small_memtypes = st.builds(MemType, small_limits)
functypes = st.builds(FuncType, valtypes, valtypes)
names = st.text(max_size=3)


def consts(t: NumType) -> st.SearchStrategy[Const]:
    """A `t.const` of a value biased to the edges of t."""
    return st.builds(Const, st.just(t), operands(t))


@dataclass(frozen=True)
class Context:
    """What a module's code may name (3.1.1's C, for the subset): each index space, imports first,
    as the types of its entries; a memory or none."""

    types: tuple[FuncType, ...]
    funcs: tuple[FuncType, ...]
    globals: tuple[GlobalType, ...]
    tables: int
    memory: bool


def context_of(module: Module) -> Context:
    """The context of `module`'s index spaces, its imports first."""
    descs = [i.desc for i in module.imports]
    funcs = [module.types[d.type] for d in descs if isinstance(d, FuncImport)]
    globals_ = [d.type for d in descs if isinstance(d, GlobalImport)]
    return Context(
        types=module.types,
        funcs=(*funcs, *(module.types[f.type] for f in module.funcs)),
        globals=(*globals_, *(g.type for g in module.globals)),
        tables=sum(isinstance(d, TableImport) for d in descs) + len(module.tables),
        memory=bool(module.mems) or any(isinstance(d, MemImport) for d in descs),
    )


def const_exprs(context: Context, t: NumType) -> st.SearchStrategy[tuple[Instr, ...]]:
    """A constant expression of type t (3.4.13): `t.const`, or `global.get` of an immutable
    global of `context`, which holds imported globals only (hole oracle-feature-set)."""
    gets = [
        GlobalGet(i) for i, g in enumerate(context.globals) if (g.mutable, g.type) == (False, t)
    ]
    single = st.sampled_from(gets) | consts(t) if gets else consts(t)
    return single.map(lambda instr: (instr,))


@st.composite
def _imports(draw: st.DrawFn, types: int) -> tuple[Import, ...]:
    """Imports of functions of the `types` type indices, tables, globals and at most one memory."""
    descs = st.one_of(
        st.builds(FuncImport, st.integers(0, types - 1)),
        st.builds(TableImport, small_tabletypes),
        st.builds(GlobalImport, globaltypes),
    )
    drawn = draw(st.lists(descs, max_size=4))
    memory = draw(st.lists(st.builds(MemImport, small_memtypes), max_size=1))
    return tuple(Import(draw(names), draw(names), desc) for desc in (*drawn, *memory))


@st.composite
def _segments(draw: st.DrawFn, head: Context, context: Context) -> dict[str, Any]:
    """Active data segments if there is a memory, active element segments if there is a table,
    their offsets constant expressions over the imported globals of `head`."""
    offsets = const_exprs(head, "i32")
    funcs = (
        st.lists(st.integers(0, len(context.funcs) - 1), max_size=3)
        if context.funcs
        else st.just([])
    )
    datas = st.builds(Data, offsets, st.binary(max_size=4))
    elems = st.builds(Elem, st.integers(0, context.tables - 1), offsets, funcs.map(tuple))
    return {
        "datas": tuple(draw(st.lists(datas, max_size=2))) if context.memory else (),
        "elems": tuple(draw(st.lists(elems, max_size=2))) if context.tables else (),
    }


def _externs(context: Context) -> list[tuple[ExternKind, int]]:
    """Every entity of `context` an export can name."""
    memory: list[tuple[ExternKind, int]] = [("memory", 0)] if context.memory else []
    return [
        *(("func", i) for i in range(len(context.funcs))),
        *(("global", i) for i in range(len(context.globals))),
        *(("table", i) for i in range(context.tables)),
        *memory,
    ]


@st.composite
def _exports(draw: st.DrawFn, context: Context) -> tuple[Export, ...]:
    """Exports of entities of `context`, under distinct names (3.5.13)."""
    externs = _externs(context)
    if not externs:
        return ()
    # Names first, with no count to reach: a unique list that must reach one can give up.
    unique = draw(st.lists(names, max_size=3, unique=True))
    targets = draw(st.lists(st.sampled_from(externs), min_size=len(unique), max_size=len(unique)))
    return tuple(
        Export(name, kind, index) for name, (kind, index) in zip(unique, targets, strict=True)
    )


@st.composite
def _start(draw: st.DrawFn, context: Context) -> int | None:
    """No start function, or one of type [] -> [] (3.5.11)."""
    starts = [i for i, f in enumerate(context.funcs) if f == FuncType((), ())]
    return draw(st.none() | st.sampled_from(starts)) if starts else None


Stack = tuple[ValType, ...]
DEPTH = 4
LENGTH = 24
"""A body nests blocks at most DEPTH deep and draws at most LENGTH instructions (design 7)."""


@dataclass
class Budget:
    """The instructions a body may still draw, shared by its nested sequences."""

    left: int


@dataclass(frozen=True)
class Frame:
    """Where code is drawn (3.1.1's C for one function): the module's context, the locals
    (params first), the function's results, and the label types, innermost first."""

    context: Context
    locals: Stack
    results: Stack
    labels: tuple[Stack, ...]
    budget: Budget

    def enter(self, label: Stack) -> "Frame":
        """The frame inside a block whose label has type `label`."""
        return replace(self, labels=(label, *self.labels))


@dataclass(frozen=True)
class Step:
    """A drawn instruction and its effect: it pops `pops` operands and pushes `pushes`; after one
    that `ends` (an unconditional transfer) the stack is polymorphic and the sequence stops."""

    instr: Instr
    pops: int
    pushes: Stack
    ends: bool = False


Move = Callable[[st.DrawFn], Step]
Entry = Callable[[Frame, Stack], Move | None]
"""An instruction class's entry: given the frame and the operand stack, None if no instruction
of the class fits, else the move that draws one that does."""


def _suffix(stack: Stack, types: Stack) -> bool:
    """Whether `types` are the top of `stack`, the last on top."""
    return len(stack) >= len(types) and stack[len(stack) - len(types) :] == types


def _close(draw: st.DrawFn, stack: Stack, results: Stack) -> list[Instr]:
    """Instructions turning `stack` into exactly `results`: drop down to the longest common
    prefix, then push a constant of each missing type."""
    keep = 0
    while keep < min(len(stack), len(results)) and stack[keep] == results[keep]:
        keep += 1
    return [*(Drop() for _ in stack[keep:]), *(draw(consts(t)) for t in results[keep:])]


def _sequence(draw: st.DrawFn, frame: Frame, stack: Stack, results: Stack) -> tuple[Instr, ...]:
    """A sequence typed `stack -> results` in `frame`: drawn steps, each fitting the stack it
    meets, then the instructions that close it, unless a step transferred control."""
    body: list[Instr] = []
    for _ in range(draw(st.integers(0, 8))):
        if frame.budget.left == 0:
            break
        frame.budget.left -= 1
        moves = [move for entry in TYPED.values() if (move := entry(frame, stack)) is not None]
        step = draw(st.sampled_from(moves))(draw)
        body.append(step.instr)
        if step.ends:
            return tuple(body)
        stack = stack[: len(stack) - step.pops] + step.pushes
    return (*body, *_close(draw, stack, results))


@st.composite
def bodies(draw: st.DrawFn, context: Context, func: Func) -> tuple[Instr, ...]:
    """A body for `func` in `context`, typed by construction to produce exactly its results."""
    signature = context.types[func.type]
    locals_ = (*signature.params, *func.locals)
    results = signature.results
    frame = Frame(context, locals_, results, (results,), Budget(LENGTH))
    return _sequence(draw, frame, (), results)


def _step(step: Step) -> Move:
    """The move that draws nothing and takes `step`."""
    return lambda _draw: step


Numeric = Unop | Binop | Testop | Relop


def _numeric(pool: tuple[Numeric, ...], arity: int, result: NumType | None) -> Entry:
    """The entry of a numeric class over `pool`: `arity` operands of one type t on top, pushing
    `result`, or t when None."""

    def entry(_frame: Frame, stack: Stack) -> Move | None:
        top = set(stack[len(stack) - arity :])
        if len(stack) < arity or len(top) != 1:
            return None
        (t,) = top
        choices = [instr for instr in pool if instr.type == t]
        return lambda draw: Step(draw(st.sampled_from(choices)), arity, (result or t,))

    return entry


def _cvtop(_frame: Frame, stack: Stack) -> Move | None:
    """A conversion from the type on top."""
    choices = [c for c in CVTOPS if stack[-1:] == (c.source,)]
    if not choices:
        return None
    return lambda draw: _converted(draw(st.sampled_from(choices)))


def _converted(c: Cvtop) -> Step:
    return Step(c, 1, (c.to,))


def _nop(_frame: Frame, _stack: Stack) -> Move:
    return _step(Step(Nop(), 0, ()))


def _unreachable(_frame: Frame, _stack: Stack) -> Move:
    return _step(Step(Unreachable(), 0, (), ends=True))


def _drop(_frame: Frame, stack: Stack) -> Move | None:
    return _step(Step(Drop(), 1, ())) if stack else None


def _select(_frame: Frame, stack: Stack) -> Move | None:
    """`select`, plain or typed with exactly one type, over two operands of one type."""
    if len(stack) < 3 or stack[-1] != "i32" or stack[-2] != stack[-3]:
        return None
    t = stack[-2]
    return lambda draw: Step(Select(draw(st.sampled_from([None, (t,)]))), 3, (t,))


def _indexed(indices: list[int], step: Callable[[int], Step]) -> Move | None:
    """The move that draws one of `indices` and takes its step; None if there are none."""
    if not indices:
        return None
    return lambda draw: step(draw(st.sampled_from(indices)))


def _local_get(frame: Frame, _stack: Stack) -> Move | None:
    return _indexed(
        list(range(len(frame.locals))), lambda x: Step(LocalGet(x), 0, (frame.locals[x],))
    )


def _local_set(frame: Frame, stack: Stack) -> Move | None:
    fits = [x for x, t in enumerate(frame.locals) if stack[-1:] == (t,)]
    return _indexed(fits, lambda x: Step(LocalSet(x), 1, ()))


def _local_tee(frame: Frame, stack: Stack) -> Move | None:
    fits = [x for x, t in enumerate(frame.locals) if stack[-1:] == (t,)]
    return _indexed(fits, lambda x: Step(LocalTee(x), 1, (frame.locals[x],)))


def _global_get(frame: Frame, _stack: Stack) -> Move | None:
    globals_ = frame.context.globals
    return _indexed(
        list(range(len(globals_))), lambda x: Step(GlobalGet(x), 0, (globals_[x].type,))
    )


def _global_set(frame: Frame, stack: Stack) -> Move | None:
    fits = [x for x, g in enumerate(frame.context.globals) if g.mutable and stack[-1:] == (g.type,)]
    return _indexed(fits, lambda x: Step(GlobalSet(x), 1, ()))


def _signature(context: Context, bt: BlockType) -> tuple[Stack, Stack]:
    """The params and results of a block type (3.2.8)."""
    match bt:
        case None:
            return (), ()
        case str():
            return (), (bt,)
        case TypeUse(index):
            return context.types[index].params, context.types[index].results
        case _:
            assert_never(bt)


def _open(draw: st.DrawFn, frame: Frame, stack: Stack) -> tuple[BlockType, Stack, Stack]:
    """A block type whose params are the top of `stack`, with its params and results."""
    uses = [TypeUse(i) for i, t in enumerate(frame.context.types) if _suffix(stack, t.params)]
    bt: BlockType = draw(st.sampled_from([None, *NUMTYPES, *uses]))
    return (bt, *_signature(frame.context, bt))


def _block(frame: Frame, stack: Stack) -> Move | None:
    """`block`, its label typed by its results."""
    if len(frame.labels) > DEPTH:
        return None

    def move(draw: st.DrawFn) -> Step:
        bt, params, results = _open(draw, frame, stack)
        body = _sequence(draw, frame.enter(results), params, results)
        return Step(Block(bt, body), len(params), results)

    return move


def _loop(frame: Frame, stack: Stack) -> Move | None:
    """`loop`, its label typed by its params."""
    if len(frame.labels) > DEPTH:
        return None

    def move(draw: st.DrawFn) -> Step:
        bt, params, results = _open(draw, frame, stack)
        body = _sequence(draw, frame.enter(params), params, results)
        return Step(Loop(bt, body), len(params), results)

    return move


def _if(frame: Frame, stack: Stack) -> Move | None:
    """`if` over an i32 on top of its params, both arms typed params -> results."""
    if len(frame.labels) > DEPTH or stack[-1:] != ("i32",):
        return None

    def move(draw: st.DrawFn) -> Step:
        bt, params, results = _open(draw, frame, stack[:-1])
        then = _sequence(draw, frame.enter(results), params, results)
        else_ = _sequence(draw, frame.enter(results), params, results)
        return Step(If(bt, then, else_), len(params) + 1, results)

    return move


def _br(frame: Frame, stack: Stack) -> Move | None:
    fits = [d for d, label in enumerate(frame.labels) if _suffix(stack, label)]
    return _indexed(fits, lambda d: Step(Br(d), 0, (), ends=True))


def _br_if(frame: Frame, stack: Stack) -> Move | None:
    below = stack[:-1]
    labels = frame.labels
    fits = [d for d, label in enumerate(labels) if stack[-1:] == ("i32",) and _suffix(below, label)]
    return _indexed(fits, lambda d: Step(BrIf(d), len(labels[d]) + 1, labels[d]))


def _br_table(frame: Frame, stack: Stack) -> Move | None:
    """`br_table` to a default label whose type is on the stack, and others of the same type."""
    labels = frame.labels
    below = stack[:-1]
    fits = [d for d, label in enumerate(labels) if stack[-1:] == ("i32",) and _suffix(below, label)]

    def step(draw: st.DrawFn, default: int) -> Step:
        same = [d for d, label in enumerate(labels) if label == labels[default]]
        targets = draw(st.lists(st.sampled_from(same), max_size=3))
        return Step(BrTable(tuple(targets), default), 0, (), ends=True)

    return _indexed_draw(fits, step)


def _indexed_draw(indices: list[int], step: Callable[[st.DrawFn, int], Step]) -> Move | None:
    """As `_indexed`, for a step that draws more after its index."""
    if not indices:
        return None
    return lambda draw: step(draw, draw(st.sampled_from(indices)))


def _return(frame: Frame, stack: Stack) -> Move | None:
    return _step(Step(Return(), 0, (), ends=True)) if _suffix(stack, frame.results) else None


def _call(frame: Frame, stack: Stack) -> Move | None:
    funcs = frame.context.funcs
    fits = [x for x, f in enumerate(funcs) if _suffix(stack, f.params)]
    return _indexed(fits, lambda x: Step(Call(x), len(funcs[x].params), funcs[x].results))


def _return_call(frame: Frame, stack: Stack) -> Move | None:
    """`return_call` of a function whose results are the caller's (3.4.2)."""
    funcs = frame.context.funcs
    fits = [
        x for x, f in enumerate(funcs) if f.results == frame.results and _suffix(stack, f.params)
    ]
    return _indexed(fits, lambda x: Step(ReturnCall(x), 0, (), ends=True))


def _indirect_types(frame: Frame, stack: Stack, tail: bool) -> list[int]:
    """The type indices an indirect call can use over an i32 on `stack`, in a module with a
    table; for a tail call, only those whose results are the caller's."""
    if not frame.context.tables or stack[-1:] != ("i32",):
        return []
    return [
        y
        for y, t in enumerate(frame.context.types)
        if _suffix(stack[:-1], t.params) and (not tail or t.results == frame.results)
    ]


def _call_indirect(frame: Frame, stack: Stack) -> Move | None:
    types = frame.context.types
    tables = st.integers(0, frame.context.tables - 1)

    def step(draw: st.DrawFn, y: int) -> Step:
        call = CallIndirect(draw(tables), TypeUse(y))
        return Step(call, len(types[y].params) + 1, types[y].results)

    return _indexed_draw(_indirect_types(frame, stack, tail=False), step)


def _return_call_indirect(frame: Frame, stack: Stack) -> Move | None:
    tables = st.integers(0, frame.context.tables - 1)

    def step(draw: st.DrawFn, y: int) -> Step:
        return Step(ReturnCallIndirect(draw(tables), TypeUse(y)), 0, (), ends=True)

    return _indexed_draw(_indirect_types(frame, stack, tail=True), step)


def _aligned[M: (Load, Store)](draw: st.DrawFn, instr: M, bits: int) -> M:
    """`instr` with a drawn offset and an alignment no greater than natural for `bits` (3.4.5)."""
    natural = (bits // 8).bit_length() - 1
    return _rearg(instr, MemArg(draw(st.integers(0, natural)), draw(u32s)))


def _load(frame: Frame, stack: Stack) -> Move | None:
    """A load, plain or narrow, from an i32 address, in a module with a memory."""
    if not frame.context.memory or stack[-1:] != ("i32",):
        return None

    def move(draw: st.DrawFn) -> Step:
        load = draw(st.sampled_from(LOADS))
        bits = load.pack[0] if load.pack else WIDTH[load.type]
        return Step(_aligned(draw, load, bits), 1, (load.type,))

    return move


def _store(frame: Frame, stack: Stack) -> Move | None:
    """A store, plain or narrow, of the value on top to an i32 address below it."""
    choices = [store for store in STORES if stack[-2:] == ("i32", store.type)]
    if not frame.context.memory or not choices:
        return None

    def move(draw: st.DrawFn) -> Step:
        store = draw(st.sampled_from(choices))
        return Step(_aligned(draw, store, store.size or WIDTH[store.type]), 2, ())

    return move


def _memory_size(frame: Frame, _stack: Stack) -> Move | None:
    return _step(Step(MemorySize(), 0, ("i32",))) if frame.context.memory else None


def _const(_frame: Frame, _stack: Stack) -> Move:
    def move(draw: st.DrawFn) -> Step:
        c = draw(numtypes.flatmap(consts))
        return Step(c, 0, (c.type,))

    return move


TYPED: dict[type[Instr], Entry] = {
    Const: _const,
    Unop: _numeric(UNOPS, 1, None),
    Binop: _numeric(BINOPS, 2, None),
    Testop: _numeric(TESTOPS, 1, "i32"),
    Relop: _numeric(RELOPS, 2, "i32"),
    Cvtop: _cvtop,
    Nop: _nop,
    Unreachable: _unreachable,
    Drop: _drop,
    Select: _select,
    LocalGet: _local_get,
    LocalSet: _local_set,
    LocalTee: _local_tee,
    GlobalGet: _global_get,
    GlobalSet: _global_set,
    Block: _block,
    Loop: _loop,
    If: _if,
    Br: _br,
    BrIf: _br_if,
    BrTable: _br_table,
    Return: _return,
    Call: _call,
    CallIndirect: _call_indirect,
    ReturnCall: _return_call,
    ReturnCallIndirect: _return_call_indirect,
    Load: _load,
    Store: _store,
    MemorySize: _memory_size,
}
"""The typed entry of each instruction class: what of it fits a given operand stack."""


@st.composite
def valid_modules(draw: st.DrawFn, closed: bool = False) -> Module:
    """A module every validator accepts; `closed` has no imports and no start function."""
    base = draw(st.lists(functypes, min_size=1, max_size=3))
    types = (*base, *draw(st.lists(st.sampled_from(base), max_size=2)))
    imports = () if closed else draw(_imports(len(types)))
    head = context_of(Module(types=types, imports=imports))
    globals_ = tuple(
        Global(t, draw(const_exprs(head, t.type))) for t in draw(st.lists(globaltypes, max_size=3))
    )
    shells = Module(
        types=types,
        imports=imports,
        globals=globals_,
        mems=()
        if head.memory
        else tuple(draw(st.lists(st.builds(Mem, small_memtypes), max_size=1))),
        tables=tuple(draw(st.lists(st.builds(Table, small_tabletypes), max_size=2))),
        funcs=tuple(
            draw(
                st.lists(
                    st.builds(Func, st.integers(0, len(types) - 1), valtypes, st.just(())),
                    max_size=3,
                )
            )
        ),
    )
    context = context_of(shells)
    funcs = tuple(replace(f, body=draw(bodies(context, f))) for f in shells.funcs)
    return replace(
        shells,
        funcs=funcs,
        **draw(_segments(head, context)),
        start=None if closed else draw(_start(context)),
        exports=draw(_exports(context)),
    )
