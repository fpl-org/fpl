"""The text format of WebAssembly, spec 6: `print_module` writes a module as flat WAT.

One module field per line in the order of 2.5 (imports first, as 6.6.13 requires), one
instruction per line, `block`/`loop`/`if ... else ... end` bracketed and indented, numeric
indices everywhere (no symbolic identifiers), constants in unsigned decimal, `offset=` and
`align=` only when not the default, and strings and data with every byte outside printable
ASCII, and every quote and backslash, as `\\hh`. The printer is total on the model, deterministic
and injective (two different modules print differently); it is not a formatter for humans.
"""

from collections.abc import Callable
from dataclasses import fields
from typing import Any

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
    Data,
    Elem,
    Export,
    Expr,
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
from fpl.asm.wasm.types import WIDTH, BlockType, FuncType, GlobalType, Limits, TableType, ValType


def print_module(module: Module) -> str:
    """The module as WAT text (6.6), ending in a newline."""
    fields_ = [
        *map(_type, module.types),
        *map(_import, module.imports),
        *map(_global, module.globals),
        *map(_memory, module.mems),
        *map(_table, module.tables),
        *map(_func, module.funcs),
        *map(_data, module.datas),
        *map(_elem, module.elems),
        *_start(module.start),
        *map(_export, module.exports),
    ]
    return "(module" + "".join("\n  " + field for field in fields_) + ")\n"


def _lines(instr: Instr) -> list[str]:
    """The lines of one instruction: a structured one brackets its bodies, a plain one is one."""
    nested = _NESTED.get(type(instr))
    return nested(instr) if nested else [_PLAIN[type(instr)](instr)]


def _body(instrs: Expr) -> list[str]:
    """The lines of a sequence of instructions, each indented one step inside its bracket."""
    return ["  " + line for instr in instrs for line in _lines(instr)]


def _blocktype(t: BlockType) -> str:
    """A block type (6.5.3): nothing, ` (result t)`, or ` (type x)`."""
    match t:
        case None:
            return ""
        case str():
            return f" (result {t})"
        case _:
            return f" (type {t.index})"


def _block(instr: Block | Loop) -> list[str]:
    """`block` or `loop`, its block type, its body, `end`."""
    return [_MNEMONIC[type(instr)] + _blocktype(instr.type), *_body(instr.body), "end"]


def _if(instr: If) -> list[str]:
    """`if`, then `else` always (an empty arm prints as nothing between the keywords), `end`."""
    return [f"if{_blocktype(instr.type)}", *_body(instr.then), "else", *_body(instr.else_), "end"]


def _typed(instr: Unop | Binop | Testop | Relop) -> str:
    """`t.op`: a numeric instruction, its number type and operator (6.5.9)."""
    return f"{instr.type}.{instr.op}"


def _const(instr: Const) -> str:
    """`t.const c`, the value in unsigned decimal (6.5.9)."""
    return f"{instr.type}.const {instr.value}"


def _cvtop(instr: Cvtop) -> str:
    """`i32.wrap_i64`, `i64.extend_i32_s`, `i64.extend_i32_u` (6.5.9)."""
    head, _, sign = instr.op.partition("_")
    return f"{instr.to}.{head}_{instr.source}" + (f"_{sign}" if sign else "")


def _select(instr: Select) -> str:
    """`select`, or typed `select (result t*)`, `select (result)` for no types (6.5.2)."""
    if instr.types is None:
        return "select"
    return f"select (result{''.join(' ' + t for t in instr.types)})"


def _plain(instr: Instr) -> str:
    """The mnemonic, then each immediate in field order: `return`, `br 1`, `local.get 0`."""
    immediates = (str(getattr(instr, f.name)) for f in fields(instr))
    return " ".join([_MNEMONIC[type(instr)], *immediates])


def _br_table(instr: BrTable) -> str:
    """`br_table l* l_N` (6.5.3)."""
    return " ".join(["br_table", *map(str, instr.labels), str(instr.default)])


def _indirect(instr: CallIndirect | ReturnCallIndirect) -> str:
    """`call_indirect x (type y)` and its tail form (6.5.3), the table index always printed."""
    return f"{_MNEMONIC[type(instr)]} {instr.table} (type {instr.type.index})"


def _memarg(arg: MemArg, bits: int) -> str:
    """` offset=o` unless 0, ` align=2**a` unless the natural alignment of `bits` (6.5.6)."""
    natural = (bits // 8).bit_length() - 1
    offset = f" offset={arg.offset}" if arg.offset else ""
    return offset + (f" align={1 << arg.align}" if arg.align != natural else "")


def _load(instr: Load) -> str:
    """`t.load` or `t.loadN_sx`, then its memarg (6.5.6)."""
    if instr.pack is None:
        return f"{instr.type}.load{_memarg(instr.arg, WIDTH[instr.type])}"
    bits, sign = instr.pack
    return f"{instr.type}.load{bits}_{sign}{_memarg(instr.arg, bits)}"


def _store(instr: Store) -> str:
    """`t.store` or `t.storeN`, then its memarg (6.5.6)."""
    suffix = "" if instr.size is None else str(instr.size)
    return f"{instr.type}.store{suffix}{_memarg(instr.arg, instr.size or WIDTH[instr.type])}"


_MNEMONIC: dict[type[Instr], str] = {
    Nop: "nop", Unreachable: "unreachable", Drop: "drop", Return: "return",
    Block: "block", Loop: "loop", Br: "br", BrIf: "br_if",
    Call: "call", ReturnCall: "return_call",
    CallIndirect: "call_indirect", ReturnCallIndirect: "return_call_indirect",
    LocalGet: "local.get", LocalSet: "local.set", LocalTee: "local.tee",
    GlobalGet: "global.get", GlobalSet: "global.set", MemorySize: "memory.size",
}  # fmt: skip
"""The keyword of each instruction whose printer does not spell it out."""

_PLAIN: dict[type[Instr], Callable[[Any], str]] = {
    Const: _const, Unop: _typed, Binop: _typed, Testop: _typed, Relop: _typed, Cvtop: _cvtop,
    Select: _select, BrTable: _br_table, Load: _load, Store: _store,
    CallIndirect: _indirect, ReturnCallIndirect: _indirect,
    **dict.fromkeys((
        Nop, Unreachable, Drop, Return, Br, BrIf, Call, ReturnCall,
        LocalGet, LocalSet, LocalTee, GlobalGet, GlobalSet, MemorySize,
    ), _plain),
}  # fmt: skip
"""The printer of each plain instruction class; a table, so no printer nears complexity 8."""

_NESTED: dict[type[Instr], Callable[[Any], list[str]]] = {Block: _block, Loop: _block, If: _if}
"""The printer of each structured instruction class, which prints several lines."""


def _field(head: str, body: Expr, tail: str = "") -> str:
    """A module field holding an expression: its head, the expression one instruction per
    line, then `tail` and the closing parenthesis."""
    lines = (line for instr in body for line in _lines(instr))
    return "\n    ".join([head, *lines]) + tail + ")"


def _valtypes(keyword: str, types: tuple[ValType, ...]) -> str:
    """` (param i32 i64)` and the like (6.4.6); nothing for no types."""
    return f" ({keyword} {' '.join(types)})" if types else ""


def _limits(limits: Limits) -> str:
    """`min` or `min max` (6.4.9)."""
    return str(limits.min) if limits.max is None else f"{limits.min} {limits.max}"


def _table_type(t: TableType) -> str:
    """A table type (6.4.13), its element type written `funcref`."""
    return f"{_limits(t.limits)} funcref"


def _global_type(t: GlobalType) -> str:
    """`t` or `(mut t)` (6.4.11)."""
    return f"(mut {t.type})" if t.mutable else t.type


def _type(t: FuncType) -> str:
    """A type definition (6.6.2), a function type."""
    return f"(type (func{_valtypes('param', t.params)}{_valtypes('result', t.results)}))"


_DESC: dict[type[ImportDesc], Callable[[Any], str]] = {
    FuncImport: lambda d: f"(func (type {d.type}))",
    TableImport: lambda d: f"(table {_table_type(d.type)})",
    MemImport: lambda d: f"(memory {_limits(d.type.limits)})",
    GlobalImport: lambda d: f"(global {_global_type(d.type)})",
}
"""The printer of each import description (6.6.4)."""


def _import(i: Import) -> str:
    """An import (6.6.4)."""
    names = f"{_string(i.module.encode())} {_string(i.name.encode())}"
    return f"(import {names} {_DESC[type(i.desc)](i.desc)})"


def _memory(m: Mem) -> str:
    """A memory (6.6.9)."""
    return f"(memory {_limits(m.type.limits)})"


def _table(t: Table) -> str:
    """A table (6.6.10) with no initializer: every element null."""
    return f"(table {_table_type(t.type)})"


def _start(start: int | None) -> tuple[str, ...]:
    """The start field (6.6.13), if the module has one."""
    return () if start is None else (f"(start {start})",)


def _global(g: Global) -> str:
    """A global (6.6.8): its type, then its initializer one instruction per line."""
    return _field(f"(global {_global_type(g.type)}", g.init)


def _func(f: Func) -> str:
    """A function (6.6.7): its type use, its locals, then its body one instruction per line."""
    return _field(f"(func (type {f.type}){_valtypes('local', f.locals)}", f.body)


def _data(d: Data) -> str:
    """An active data segment on memory 0 (6.6.11): its offset expression, then its bytes."""
    return _field("(data (offset", d.offset, f") {_string(d.init)}")


def _elem(e: Elem) -> str:
    """An active element segment (6.6.10): table use, offset, then `func` and its indices."""
    funcs = "".join(f" {x}" for x in e.funcs)
    return _field(f"(elem (table {e.table}) (offset", e.offset, f") func{funcs}")


def _string(data: bytes) -> str:
    """A string literal (6.3.3) holding `data`."""
    escaped = (chr(b) if 0x20 <= b < 0x7F and b not in b'"\\' else f"\\{b:02x}" for b in data)
    return '"' + "".join(escaped) + '"'


def _export(e: Export) -> str:
    """An export (6.6.12)."""
    return f"(export {_string(e.name.encode())} ({e.kind} {e.index}))"
