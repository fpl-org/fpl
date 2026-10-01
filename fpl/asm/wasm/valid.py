"""Validation of WebAssembly, spec 3, for the subset of `fpl.asm.wasm`: `check` a module.

Instruction sequences are checked by the spec's own algorithm, appendix 7.6.1 (the operand
stack of value types or Unknown, the control stack of frames) and 7.6.2 (`pop_val`,
`push_ctrl`, `pop_ctrl`, `label_types`, `unreachable`), one small function per instruction
family in a dispatch table, each citing its 3.4.x rule. Module fields follow 3.5 in an order
that checks every index a later pass relies on first: type indices, limits, then globals,
function bodies, data and element segments, the start function and the exports.

Constant expressions (3.4.13) are the 2.0 rule both oracles accept: `t.const`, or `global.get`
of an imported immutable global (HOLES.md oracle-feature-set), in every constant expression.
`check` returns the first rule a module breaks as `Invalid`, or None if it is valid; it never
raises on a module the model can hold.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, assert_never

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
    If,
    Instr,
    Load,
    LocalGet,
    LocalSet,
    LocalTee,
    Loop,
    MemArg,
    MemorySize,
    Nop,
    Relop,
    Return,
    ReturnCall,
    ReturnCallIndirect,
    Select,
    Store,
    Testop,
    Unop,
    Unreachable,
)
from fpl.asm.wasm.module import (
    Expr,
    Func,
    FuncImport,
    Global,
    GlobalImport,
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
    TableType,
    TypeUse,
    ValType,
)

InvalidKind = Literal[
    "mismatch", "underflow", "leftover", "label", "br-table-arity",
    "local", "global", "func", "type", "table", "memory",
    "immutable", "align", "tail-result", "const", "start", "export-name", "limits",
]  # fmt: skip
"""Why a module is invalid: an operand of the wrong type, including a typed `select` without
exactly one type (mismatch); a pop below the current frame (underflow); values left at the end
of a block, function or constant expression (leftover); a branch past the control stack
(label); `br_table` targets of different arities; an index out of its space, or no memory or
table (local ... memory); `global.set` of an immutable global; an alignment past the natural
one; a tail call whose callee's results are not the caller's (tail-result); a non-constant
instruction in a constant expression; a start function not [] -> []; a duplicate export name;
limits with min > max or beyond their bound."""


@dataclass(frozen=True, slots=True)
class Invalid:
    """The first rule a module breaks, and where: the index of the entry in its module field (a
    function by its function index, imports first), then the path of the instruction in nested
    bodies, an `if`'s else arm numbered on from its then arm. Empty for none of these."""

    kind: InvalidKind
    where: tuple[int, ...]


class _RefusedError(Exception):
    """Carries the first `Invalid` out of the passes, to `check`."""

    def __init__(self, invalid: Invalid) -> None:
        super().__init__(invalid)
        self.invalid = invalid


def _refuse_if(bad: bool, kind: InvalidKind, where: tuple[int, ...] = ()) -> None:
    if bad:
        raise _RefusedError(Invalid(kind, where))


def _lookup[T](space: tuple[T, ...], index: int, kind: InvalidKind) -> T:
    """Entry `index` of an index space; refused as `kind` when out of range."""
    _refuse_if(not 0 <= index < len(space), kind)
    return space[index]


PAGES = 1 << 16
"""The bound of a memory's limits, in 64 KiB pages (3.2.12, 3.2.15)."""
ELEMENTS = (1 << 32) - 1
"""The bound of a table's limits, in elements (3.2.12, 3.2.16)."""


def limits_valid(limits: Limits, bound: int) -> bool:
    """3.2.12: min from 0 up to `bound`, and max, if any, from min up to `bound`; the model
    holds any int, so a negative one, which no format can write, is refused here."""
    return 0 <= limits.min <= bound and (limits.max is None or limits.min <= limits.max <= bound)


@dataclass(frozen=True, slots=True)
class Context:
    """3.1.1's C for the subset: each index space, imports first; the number of imported
    globals, the only ones a constant expression may read; whether there is a memory."""

    types: tuple[FuncType, ...]
    funcs: tuple[FuncType, ...]
    globals: tuple[GlobalType, ...]
    imported_globals: int
    tables: tuple[TableType, ...]
    memory: bool


Operand = ValType | None
"""7.6.1's val_type, None standing for Unknown."""
Types = tuple[ValType, ...]


@dataclass(slots=True)
class _Frame:
    """7.6.1's ctrl_frame; `opcode` is the block's class, None for the function's own frame."""

    opcode: type[Instr] | None
    start: Types
    end: Types
    height: int
    unreachable: bool = False


@dataclass(slots=True)
class _Code:
    """7.6.1's state while one body is checked, with the context, the locals (params first),
    C.return, whether the body is a constant expression, and the path to the instruction."""

    context: Context
    locals: Types
    results: Types
    constant: bool
    vals: list[Operand]
    ctrls: list[_Frame]
    path: list[int]


def _pop(code: _Code) -> Operand:
    """7.6.2 pop_val(): Unknown below an unreachable frame's height, refused below another's."""
    frame = code.ctrls[-1]
    if len(code.vals) == frame.height:
        _refuse_if(not frame.unreachable, "underflow")
        return None
    return code.vals.pop()


def _pop_expect(code: _Code, expect: ValType) -> Operand:
    """7.6.2 pop_val(expect): the operand popped, refused if known and not `expect`."""
    actual = _pop(code)
    _refuse_if(actual is not None and actual != expect, "mismatch")
    return actual


def _pop_vals(code: _Code, types: Types) -> list[Operand]:
    """7.6.2 pop_vals: the operands popped for `types`, in stack order."""
    popped: list[Operand] = [_pop_expect(code, t) for t in reversed(types)]
    popped.reverse()
    return popped


def _op(code: _Code, pops: Types, pushes: Types) -> None:
    _pop_vals(code, pops)
    code.vals.extend(pushes)


def _push_ctrl(code: _Code, opcode: type[Instr] | None, start: Types, end: Types) -> None:
    code.ctrls.append(_Frame(opcode, start, end, len(code.vals)))
    code.vals.extend(start)


def _pop_ctrl(code: _Code) -> _Frame:
    """7.6.2 pop_ctrl: the frame closed, refused unless its stack holds exactly its end types."""
    frame = code.ctrls[-1]
    _pop_vals(code, frame.end)
    _refuse_if(len(code.vals) != frame.height, "leftover")
    code.ctrls.pop()
    return frame


def _unreachable(code: _Code) -> None:
    """7.6.2 unreachable(): the rest of the frame is stack-polymorphic."""
    frame = code.ctrls[-1]
    del code.vals[frame.height :]
    frame.unreachable = True


def _label(code: _Code, depth: int) -> Types:
    """7.6.2 label_types of the frame `depth` from the top: a loop's start, else its end."""
    _refuse_if(not 0 <= depth < len(code.ctrls), "label")
    frame = code.ctrls[-1 - depth]
    return frame.start if frame.opcode is Loop else frame.end


def _sequence(code: _Code, instrs: Expr, first: int = 0) -> None:
    """Each instruction in turn, numbered from `first` in the path (3.4.12)."""
    for position, instr in enumerate(instrs, first):
        code.path.append(position)
        _refuse_if(code.constant and not isinstance(instr, Const | GlobalGet), "const")
        _FAMILIES[type(instr)](code, instr)
        code.path.pop()


_NUMERIC: dict[type[Instr], Callable[[Any], tuple[Types, Types]]] = {
    Const: lambda i: ((), (i.type,)),
    Unop: lambda i: ((i.type,), (i.type,)),
    Binop: lambda i: ((i.type, i.type), (i.type,)),
    Testop: lambda i: ((i.type,), ("i32",)),
    Relop: lambda i: ((i.type, i.type), ("i32",)),
    Cvtop: lambda i: ((i.source,), (i.to,)),
}
"""3.4.10: what each numeric instruction pops and pushes."""


def _numeric(code: _Code, instr: Const | Unop | Binop | Testop | Relop | Cvtop) -> None:
    """3.4.10, the numeric instructions: fixed operand and result types."""
    _op(code, *_NUMERIC[type(instr)](instr))


def _nop(_code: _Code, _instr: Nop) -> None:
    """3.4.1, nop: [] -> []."""


def _unreachable_instr(code: _Code, _instr: Unreachable) -> None:
    """3.4.1, unreachable: [t1*] -> [t2*], stack-polymorphic."""
    _unreachable(code)


def _drop(code: _Code, _instr: Drop) -> None:
    """3.4.1, drop: [t] -> []."""
    _pop(code)


def _select(code: _Code, instr: Select) -> None:
    """3.4.1, select: [t t i32] -> [t], t named by exactly one type when typed; plain, the two
    operands of one type, either of them Unknown."""
    if instr.types is not None:
        _refuse_if(len(instr.types) != 1, "mismatch")
        _op(code, (*instr.types * 2, "i32"), instr.types)
        return
    _pop_expect(code, "i32")
    first, second = _pop(code), _pop(code)
    _refuse_if(None not in (first, second) and first != second, "mismatch")
    code.vals.append(second if first is None else first)


def _local_get(code: _Code, instr: LocalGet) -> None:
    """3.4.3, local.get x: [] -> [t], t the type of local x."""
    code.vals.append(_lookup(code.locals, instr.index, "local"))


def _local_set(code: _Code, instr: LocalSet) -> None:
    """3.4.3, local.set x: [t] -> []."""
    _pop_expect(code, _lookup(code.locals, instr.index, "local"))


def _local_tee(code: _Code, instr: LocalTee) -> None:
    """3.4.3, local.tee x: [t] -> [t]."""
    t: ValType = _lookup(code.locals, instr.index, "local")
    _op(code, (t,), (t,))


def _global_get(code: _Code, instr: GlobalGet) -> None:
    """3.4.3, global.get x: [] -> [t]; in a constant expression x is imported and immutable."""
    g = _lookup(code.context.globals, instr.index, "global")
    imported = instr.index < code.context.imported_globals
    _refuse_if(code.constant and (g.mutable or not imported), "const")
    code.vals.append(g.type)


def _global_set(code: _Code, instr: GlobalSet) -> None:
    """3.4.3, global.set x: [t] -> [], x mutable."""
    g = _lookup(code.context.globals, instr.index, "global")
    _refuse_if(not g.mutable, "immutable")
    _pop_expect(code, g.type)


def _blocktype(code: _Code, bt: BlockType) -> FuncType:
    """3.2.8: a block type as a function type."""
    match bt:
        case TypeUse(index):
            return _lookup(code.context.types, index, "type")
        case "i32" | "i64":
            return FuncType((), (bt,))
        case None:
            return FuncType((), ())
        case _:
            assert_never(bt)


def _end(code: _Code) -> None:
    """7.6.2 end: close the frame, push its end types."""
    code.vals.extend(_pop_ctrl(code).end)


def _block(code: _Code, instr: Block | Loop) -> None:
    """3.4.2, block and loop bt: [t1*] -> [t2*], the body checked in a new frame."""
    signature = _blocktype(code, instr.type)
    _pop_vals(code, signature.params)
    _push_ctrl(code, type(instr), signature.params, signature.results)
    _sequence(code, instr.body)
    _end(code)


def _if(code: _Code, instr: If) -> None:
    """3.4.2, if bt: [t1* i32] -> [t2*], each arm checked as a block of type bt."""
    signature = _blocktype(code, instr.type)
    _pop_expect(code, "i32")
    _pop_vals(code, signature.params)
    _push_ctrl(code, If, signature.params, signature.results)
    _sequence(code, instr.then)
    frame = _pop_ctrl(code)
    _push_ctrl(code, If, frame.start, frame.end)
    _sequence(code, instr.else_, len(instr.then))
    _end(code)


def _br(code: _Code, instr: Br) -> None:
    """3.4.2, br l: [t1* t*] -> [t2*], t* the label's types; stack-polymorphic."""
    _pop_vals(code, _label(code, instr.label))
    _unreachable(code)


def _br_if(code: _Code, instr: BrIf) -> None:
    """3.4.2, br_if l: [t* i32] -> [t*]."""
    types = _label(code, instr.label)
    _op(code, (*types, "i32"), types)


def _br_table(code: _Code, instr: BrTable) -> None:
    """3.4.2, br_table l* l_N: [t1* t* i32] -> [t2*], every label of l_N's arity, each target's
    types popped and the operands popped pushed back (Unknown stays Unknown); stack-polymorphic."""
    _pop_expect(code, "i32")
    default = _label(code, instr.default)
    for label in instr.labels:
        types = _label(code, label)
        _refuse_if(len(types) != len(default), "br-table-arity")
        code.vals.extend(_pop_vals(code, types))
    _pop_vals(code, default)
    _unreachable(code)


def _return(code: _Code, _instr: Return) -> None:
    """3.4.2, return: [t1* t*] -> [t2*], t* the function's results; stack-polymorphic."""
    _pop_vals(code, code.results)
    _unreachable(code)


def _call(code: _Code, instr: Call) -> None:
    """3.4.2, call x: the type of function x."""
    signature = _lookup(code.context.funcs, instr.func, "func")
    _op(code, signature.params, signature.results)


def _indirect(code: _Code, instr: CallIndirect | ReturnCallIndirect) -> FuncType:
    """3.4.2: the table must exist, then the type."""
    _lookup(code.context.tables, instr.table, "table")
    return _lookup(code.context.types, instr.type.index, "type")


def _call_indirect(code: _Code, instr: CallIndirect) -> None:
    """3.4.2, call_indirect x y: [t1* i32] -> [t2*], y's type."""
    signature = _indirect(code, instr)
    _op(code, (*signature.params, "i32"), signature.results)


def _tail(code: _Code, callee: FuncType, operands: Types) -> None:
    """3.4.2, a tail call: the callee's results are the caller's; stack-polymorphic after."""
    _refuse_if(callee.results != code.results, "tail-result")
    _pop_vals(code, operands)
    _unreachable(code)


def _return_call(code: _Code, instr: ReturnCall) -> None:
    """3.4.2, return_call x: [t3* t1*] -> [t4*]."""
    callee = _lookup(code.context.funcs, instr.func, "func")
    _tail(code, callee, callee.params)


def _return_call_indirect(code: _Code, instr: ReturnCallIndirect) -> None:
    """3.4.2, return_call_indirect x y: [t3* t1* i32] -> [t4*]."""
    callee = _indirect(code, instr)
    _tail(code, callee, (*callee.params, "i32"))


def _access(code: _Code, arg: MemArg, bits: int) -> None:
    """3.4.5: memory 0 exists, and the alignment is at most the natural one, bits / 8 bytes."""
    _refuse_if(not code.context.memory, "memory")
    _refuse_if(arg.align > (bits // 8).bit_length() - 1, "align")


def _load(code: _Code, instr: Load) -> None:
    """3.4.5, t.load and t.loadN_sx: [i32] -> [t]."""
    _access(code, instr.arg, instr.pack[0] if instr.pack else WIDTH[instr.type])
    _op(code, ("i32",), (instr.type,))


def _store(code: _Code, instr: Store) -> None:
    """3.4.5, t.store and t.storeN: [i32 t] -> []."""
    _access(code, instr.arg, instr.size or WIDTH[instr.type])
    _op(code, ("i32", instr.type), ())


def _memory_size(code: _Code, _instr: MemorySize) -> None:
    """3.4.5, memory.size: [] -> [i32], memory 0 exists."""
    _refuse_if(not code.context.memory, "memory")
    code.vals.append("i32")


_FAMILIES: dict[type[Instr], Callable[[_Code, Any], None]] = {
    **dict.fromkeys(_NUMERIC, _numeric),
    Nop: _nop,
    Unreachable: _unreachable_instr,
    Drop: _drop,
    Select: _select,
    LocalGet: _local_get,
    LocalSet: _local_set,
    LocalTee: _local_tee,
    GlobalGet: _global_get,
    GlobalSet: _global_set,
    Block: _block,
    Loop: _block,
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
"""The rule of each instruction class."""


def _run(code: _Code, where: int, body: Expr) -> None:
    """7.6.2 over `body`, entry `where` of its field: a frame typed [] -> C.return around the
    sequence. A refusal gains `where` and the path to the instruction that broke the rule."""
    try:
        _push_ctrl(code, None, (), code.results)
        _sequence(code, body)
        _pop_ctrl(code)
    except _RefusedError as refused:
        raise _RefusedError(Invalid(refused.invalid.kind, (where, *code.path))) from None


def _constant(context: Context, where: int, expr: Expr, t: ValType) -> None:
    """3.4.13: `expr` is a constant expression of type t, entry `where` of its field."""
    _run(_Code(context, (), (t,), True, [], [], []), where, expr)


def _imported[D](module: Module, kind: type[D]) -> list[D]:
    """The descriptions of `module`'s imports of `kind`, in order: the head of its index space."""
    return [i.desc for i in module.imports if isinstance(i.desc, kind)]


def _funcs_of(module: Module) -> list[FuncImport | Func]:
    """The function index space: imported functions, then defined ones."""
    return [*_imported(module, FuncImport), *module.funcs]


def _context(module: Module) -> Context:
    """3.1.1's C of `module`, its type indices already checked."""
    funcs = _funcs_of(module)
    globals_: list[GlobalImport | Global] = [*_imported(module, GlobalImport), *module.globals]
    tables: list[TableImport | Table] = [*_imported(module, TableImport), *module.tables]
    return Context(
        types=module.types,
        funcs=tuple(module.types[f.type] for f in funcs),
        globals=tuple(g.type for g in globals_),
        imported_globals=len(globals_) - len(module.globals),
        tables=tuple(t.type for t in tables),
        memory=bool(module.mems or _imported(module, MemImport)),
    )


def _type_indices(module: Module) -> None:
    """3.5.7, 3.5.11: every imported and defined function names a type."""
    for where, f in enumerate(_funcs_of(module)):
        _refuse_if(not 0 <= f.type < len(module.types), "type", (where,))


def _within(entries: Sequence[TableImport | Table | MemImport | Mem], bound: int) -> None:
    """3.2.12: each entry's limits valid within `bound`."""
    for where, entry in enumerate(entries):
        _refuse_if(not limits_valid(entry.type.limits, bound), "limits", (where,))


def _limits(module: Module) -> None:
    """3.2.15, 3.2.16: every table's limits within ELEMENTS, every memory's within PAGES."""
    tables: list[TableImport | Table] = [*_imported(module, TableImport), *module.tables]
    mems: list[MemImport | Mem] = [*_imported(module, MemImport), *module.mems]
    _within(tables, ELEMENTS)
    _within(mems, PAGES)


def _globals(module: Module, context: Context) -> None:
    """3.5.4: each global's initializer a constant expression of its type."""
    for where, g in enumerate(module.globals):
        _constant(context, where, g.init, g.type.type)


def _funcs(module: Module, context: Context) -> None:
    """3.5.7: each body typed by its function's type, its locals the params then the declared."""
    first = len(context.funcs) - len(module.funcs)
    for where, f in enumerate(module.funcs, first):
        signature = context.funcs[where]
        code = _Code(context, (*signature.params, *f.locals), signature.results, False, [], [], [])
        _run(code, where, f.body)


def _datas(module: Module, context: Context) -> None:
    """3.5.8: an active data segment needs memory 0 and an i32 offset."""
    for where, d in enumerate(module.datas):
        _refuse_if(not context.memory, "memory", (where,))
        _constant(context, where, d.offset, "i32")


def _elems(module: Module, context: Context) -> None:
    """3.5.9: an active element segment names a table, has an i32 offset and names functions."""
    for where, e in enumerate(module.elems):
        _refuse_if(not 0 <= e.table < len(context.tables), "table", (where,))
        _constant(context, where, e.offset, "i32")
        for func in e.funcs:
            _refuse_if(not 0 <= func < len(context.funcs), "func", (where,))


def _start(module: Module, context: Context) -> None:
    """3.5.11: the start function exists and has type [] -> []."""
    if module.start is not None:
        _refuse_if(not 0 <= module.start < len(context.funcs), "func")
        _refuse_if(context.funcs[module.start] != FuncType((), ()), "start")


def _exports(module: Module, context: Context) -> None:
    """3.5.13: each export names an entity of its kind, under a name no other export has."""
    sizes = {
        "func": len(context.funcs),
        "table": len(context.tables),
        "memory": int(context.memory),
        "global": len(context.globals),
    }
    seen: set[str] = set()
    for where, e in enumerate(module.exports):
        _refuse_if(not 0 <= e.index < sizes[e.kind], e.kind, (where,))
        _refuse_if(e.name in seen, "export-name", (where,))
        seen.add(e.name)


_PASSES = (_globals, _funcs, _datas, _elems, _start, _exports)
"""3.5.14's premises over the context, in the order `check` runs them."""


def _module(module: Module) -> None:
    _type_indices(module)
    _limits(module)
    context = _context(module)
    for check_pass in _PASSES:
        check_pass(module, context)


def check(module: Module) -> Invalid | None:
    """3.5.14: None if `module` is valid, else the first rule it breaks."""
    try:
        _module(module)
    except _RefusedError as refused:
        return refused.invalid
    return None
