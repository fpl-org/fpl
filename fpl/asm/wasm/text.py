"""The text format of WebAssembly, spec 6: `print_module` writes a module as flat WAT.

One module field per line in the order of 2.5, one instruction per line, numeric indices
everywhere (no symbolic identifiers), constants in unsigned decimal, strings with every byte
outside printable ASCII, and every quote and backslash, as `\\hh`. The printer is total on the
model and deterministic; it is not a formatter for humans.
"""

from collections.abc import Callable
from dataclasses import fields
from typing import Any

from fpl.asm.wasm.instr import Binop, Const, Instr, Return
from fpl.asm.wasm.module import Export, Func, Module
from fpl.asm.wasm.types import FuncType, ValType


def print_module(module: Module) -> str:
    """The module as WAT text (6.6), ending in a newline."""
    fields = [
        *(_type(t) for t in module.types),
        *(_func(f) for f in module.funcs),
        *(_export(e) for e in module.exports),
    ]
    return "(module" + "".join("\n  " + field for field in fields) + ")\n"


def print_instr(instr: Instr) -> str:
    """One plain instruction (6.5), as its mnemonic and immediates."""
    return _PLAIN[type(instr)](instr)


def _typed(instr: Binop) -> str:
    """`t.op`: a numeric instruction, its number type and operator (6.5.9)."""
    return f"{instr.type}.{instr.op}"


def _const(instr: Const) -> str:
    """`t.const c`, the value in unsigned decimal (6.5.9)."""
    return f"{instr.type}.const {instr.value}"


def _plain(instr: Instr) -> str:
    """The mnemonic, then each immediate in field order: `return`, `br 1`, `local.get 0`."""
    immediates = (str(getattr(instr, f.name)) for f in fields(instr))
    return " ".join([_MNEMONIC[type(instr)], *immediates])


_MNEMONIC: dict[type[Instr], str] = {Return: "return"}
"""The keyword of each instruction that `_plain` prints."""

_PLAIN: dict[type[Instr], Callable[[Any], str]] = {Const: _const, Binop: _typed, Return: _plain}
"""The printer of each plain instruction class; a table, so no printer nears complexity 8."""


def _valtypes(keyword: str, types: tuple[ValType, ...]) -> str:
    """` (param i32 i64)` and the like (6.4.6); nothing for no types."""
    return f" ({keyword} {' '.join(types)})" if types else ""


def _type(t: FuncType) -> str:
    """A type definition (6.6.2), a function type."""
    return f"(type (func{_valtypes('param', t.params)}{_valtypes('result', t.results)}))"


def _func(f: Func) -> str:
    """A function (6.6.7): its type use, its locals, then its body one instruction per line."""
    head = f"(func (type {f.type}){_valtypes('local', f.locals)}"
    return "\n    ".join([head, *(print_instr(i) for i in f.body)]) + ")"


def _string(name: str) -> str:
    """A string literal (6.3.3) holding the UTF-8 bytes of `name`."""
    escaped = (
        chr(b) if 0x20 <= b < 0x7F and b not in b'"\\' else f"\\{b:02x}" for b in name.encode()
    )
    return '"' + "".join(escaped) + '"'


def _export(e: Export) -> str:
    """An export (6.6.12)."""
    return f"(export {_string(e.name)} ({e.kind} {e.index}))"
