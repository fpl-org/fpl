"""The printer of fpl.asm.wasm writes WAT that wabt assembles, and names that survive it."""

import re

from hypothesis import given
from wasm_oracle import Tools, wat2wasm
from wasm_strategies import BinopMain, binop_mains

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
    Unop,
    Unreachable,
)
from fpl.asm.wasm.instr import Testop as _Testop  # pytest would collect a Test* name
from fpl.asm.wasm.module import (
    Data,
    Elem,
    Export,
    Func,
    FuncImport,
    Global,
    GlobalImport,
    Import,
    Mem,
    MemImport,
    Module,
    Table,
    TableImport,
)
from fpl.asm.wasm.text import print_module
from fpl.asm.wasm.types import FuncType, GlobalType, Limits, MemType, TableType, TypeUse

ZERO = Const("i32", 0)

EVERY_CONSTRUCT = Module(
    types=(FuncType((), ("i32",)), FuncType(("i32",), ("i32",)), FuncType((), ())),
    imports=(
        Import("env", "f", FuncImport(2)),
        Import("env", "t", TableImport(TableType(Limits(1, None)))),
        Import("env", "g", GlobalImport(GlobalType(False, "i32"))),
    ),
    globals=(Global(GlobalType(True, "i64"), (Const("i64", 2**64 - 1),)),),
    mems=(Mem(MemType(Limits(1, 2))),),
    tables=(Table(TableType(Limits(2, 2))),),
    funcs=(
        Func(0, ("i32", "i64"), (
            Nop(), Block(None, (Br(0),)), Loop(None, (ZERO, BrIf(0))),
            ZERO, Load("i64", MemArg(0, 4), (8, "s")), Drop(),
            ZERO, Load("i32", MemArg(1, 0), None), Drop(),
            ZERO, Const("i64", 5), Store("i64", MemArg(2, 8), 32),
            ZERO, Const("i32", 1), Store("i32", MemArg(0, 0), None),
            MemorySize(), Drop(),
            LocalGet(1), Unop("i64", "extend32_s"), Cvtop("i32", "wrap", "i64"), LocalSet(0),
            LocalGet(0), Cvtop("i64", "extend_u", "i32"), LocalTee(1),
            _Testop("i64", "eqz"), Drop(),
            GlobalGet(1), Const("i64", 1), Binop("i64", "add"), GlobalSet(1),
            Const("i32", 3), Const("i32", 4), Const("i32", 1), Const("i32", 2),
            Relop("i32", "lt_u"), Select(None), Const("i32", 5), ZERO, Select(("i32",)),
            If("i32", (Const("i32", 7),), (Const("i32", 8),)), Unop("i32", "clz"),
            Block(TypeUse(1), (ZERO, BrTable((0,), 0))),
            Call(0), ZERO, CallIndirect(0, TypeUse(2)), GlobalGet(0), Binop("i32", "add"),
            ReturnCall(2),
        )),
        Func(0, (), (ZERO, ReturnCallIndirect(1, TypeUse(0)))),
        Func(0, (), (Unreachable(),)),
        Func(0, (), (Const("i32", 9), Return())),
    ),
    datas=(Data((ZERO,), b'a"\x00'),),
    elems=(Elem(1, (ZERO,), (1, 2)),),
    start=0,
    exports=(
        Export("f1", "func", 1), Export("t", "table", 1),
        Export("m", "memory", 0), Export("g", "global", 1),
    ),
)  # fmt: skip
"""A valid module holding every instruction class, import and export kind of the subset."""


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


def test_every_construct_prints_to_wat_that_wabt_assembles_and_validates(wasm_tools: Tools) -> None:
    text = print_module(EVERY_CONSTRUCT)
    done = wat2wasm(wasm_tools, text)
    assert done.returncode == 0, f"{text}\n{done.stderr}"


def test_the_forms_wabt_cannot_meet_in_one_module_print_exactly() -> None:
    """An imported memory (a module holds one), an untyped block, a typed select of no types."""
    body = (Block("i64", ()), Select(()))
    module = Module(imports=(Import("e", "m", MemImport(MemType(Limits(0, None)))),),
                    funcs=(Func(0, (), body),))  # fmt: skip
    assert print_module(module) == (
        "(module\n"
        '  (import "e" "m" (memory 0))\n'
        "  (func (type 0)\n"
        "    block (result i64)\n"
        "    end\n"
        "    select (result)))\n"
    )
