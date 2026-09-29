"""The printer of fpl.asm.wasm writes WAT that wabt assembles, and names that survive it."""

import re

from hypothesis import given
from wasm_oracle import Tools, wat2wasm
from wasm_strategies import BinopMain, binop_mains

from fpl.asm.wasm.instr import Binop, Const, Return
from fpl.asm.wasm.module import Export, Func, Module
from fpl.asm.wasm.text import print_module
from fpl.asm.wasm.types import FuncType


def unescape(literal: str) -> bytes:
    """The bytes a WAT string literal's body stands for (6.3.3), for `\\hh` escapes only."""
    return re.sub(rb"\\([0-9a-f]{2})", lambda m: bytes([int(m[1], 16)]), literal.encode())


@given(binop_mains(unused=True))
def test_a_printed_module_assembles_and_keeps_its_export_name(
    wasm_tools: Tools, case: BinopMain
) -> None:
    module: Module = case.module()
    text = print_module(module)
    done = wat2wasm(wasm_tools, text)
    assert done.returncode == 0, f"{text}\n{done.stderr}"
    literal = re.search(r'\(export "([^"]*)" \(func 0\)\)', text)
    assert literal is not None, text
    assert unescape(literal[1]) == case.name.encode()


def test_a_module_prints_its_types_locals_and_name_exactly() -> None:
    """Params, results and locals print in order, an empty list prints nothing, and a name
    keeps printable ASCII (space included) but escapes DEL, quote, backslash and UTF-8 bytes."""
    module = Module(
        types=(FuncType(("i32", "i64"), ("i64",)), FuncType((), ())),
        funcs=(Func(0, ("i64", "i32"), (Const("i64", 7), Binop("i64", "add"), Return())),),
        exports=(Export('X \x7f"\\\u00e9', "func", 0),),
    )
    assert print_module(module) == (
        "(module\n"
        "  (type (func (param i32 i64) (result i64)))\n"
        "  (type (func))\n"
        "  (func (type 0) (local i64 i32)\n"
        "    i64.const 7\n"
        "    i64.add\n"
        "    return)\n"
        '  (export "X \\7f\\22\\5c\\c3\\a9" (func 0)))\n'
    )
