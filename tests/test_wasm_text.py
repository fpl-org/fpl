"""The printer of fpl.asm.wasm writes WAT that wabt assembles, and names that survive it."""

import contextlib
import re
from collections.abc import Iterator
from dataclasses import fields, is_dataclass, replace
from typing import TYPE_CHECKING, Any, cast, get_args

from hypothesis import given
from hypothesis import strategies as st
from wasm_oracle import Item, Tools, Verdict, run_wabt, run_wasmtime, wat2wasm
from wasm_strategies import (
    BINOPS,
    CVTOPS,
    FIELDS,
    INSTRS,
    LOADS,
    RELOPS,
    STORES,
    TESTOPS,
    TYPED,
    UNOPS,
    BinopMain,
    binop_mains,
    module_of,
    module_parts,
    valid_modules,
)

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

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


def test_every_construct_prints_to_wat_that_wabt_assembles_and_validates(
    wasm_tools: Tools,
) -> None:
    text = print_module(EVERY_CONSTRUCT)
    done = wat2wasm(wasm_tools, text)
    assert done.returncode == 0, f"{text}\n{done.stderr}"


def test_a_memarg_prints_its_offset_and_alignment_only_when_they_are_not_the_default() -> None:
    loads = {
        "i32.load": Load("i32", MemArg(2, 0), None),
        "i32.load align=2": Load("i32", MemArg(1, 0), None),
        "i32.load offset=4": Load("i32", MemArg(2, 4), None),
        "i64.load8_u": Load("i64", MemArg(0, 0), (8, "u")),
        "i64.load16_s offset=1 align=1": Load("i64", MemArg(0, 1), (16, "s")),
        "i32.load align=9223372036854775808": Load("i32", MemArg(63, 0), None),
    }
    for text, load in loads.items():
        module = Module(types=(FuncType((), ()),), funcs=(Func(0, (), (ZERO, load, Drop())),))
        assert text in [line.strip() for line in print_module(module).splitlines()], text


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


def _replaced[D: DataclassInstance](value: D, name: str, new: object) -> list[D]:
    """`value` with field `name` set to `new`, or nothing when its class refuses that."""
    try:
        return [replace(value, **{name: new})]
    except ValueError:
        return []


def one_field_off[T](value: T, donor: T) -> Iterator[T]:
    """Copies of `value` differing from it in one field at one place: at every dataclass in it
    whose counterpart in `donor` (tuples aligned by index) is of the same class, each field in
    turn taken from that counterpart; a copy its class refuses is left out."""
    node = cast("object", value)
    if type(donor) is type(node) and is_dataclass(node) and not isinstance(node, type):
        for f in fields(node):
            theirs = getattr(donor, f.name)
            yield from cast("list[T]", _replaced(node, f.name, theirs))
            for w in one_field_off(getattr(node, f.name), theirs):
                yield from cast("list[T]", _replaced(node, f.name, w))
    elif isinstance(node, tuple) and isinstance(donor, tuple):
        mine, others = (
            cast("tuple[object, ...]", node),
            cast("tuple[object, ...]", donor),
        )
        for k, (v, d) in enumerate(zip(mine, others, strict=False)):
            yield from (cast("T", (*mine[:k], w, *mine[k + 1 :])) for w in one_field_off(v, d))


def alone(instr: Instr) -> Module:
    """A module whose one function's body is `instr`."""
    return Module(funcs=(Func(0, (), (instr,)),))


@given(module_parts, st.sampled_from(sorted(FIELDS)), st.data())
def test_different_modules_print_differently(
    parts: dict[str, Any], name: str, data: st.DataObject
) -> None:
    """[law: print-injective] Two different modules print to different text: a module and
    itself with one field redrawn; a module and each copy of it with one field of one of its
    dataclasses (Limits, GlobalType, Export, Global, Data, Elem, Func, an instruction, ...)
    taken from a second drawn module; for every instruction class with fields, a module
    holding a drawn instruction and one holding it with one field taken from another draw,
    so near misses such as `select` against `select (result)` meet in every example; and
    every enumerated instance of a finite-operator class prints apart from every other."""
    finite: list[Instr] = [*UNOPS, *BINOPS, *TESTOPS, *RELOPS, *CVTOPS, *LOADS, *STORES]
    assert len({print_module(alone(instr)) for instr in finite}) == len(finite)
    redrawn = data.draw(FIELDS[name].filter(lambda value: value != parts[name]))
    first = module_of(parts)
    pairs = [(first, module_of(parts | {name: redrawn}))]
    second = module_of(data.draw(module_parts))
    pairs += [(first, other) for other in one_field_off(first, second)]
    for builder in INSTRS.values():
        one, donor = data.draw(builder), data.draw(builder)
        names = [f.name for f in fields(one)]
        if names:
            field = data.draw(st.sampled_from(names))
            with contextlib.suppress(ValueError):  # a mixed pair the class refuses is no module
                pairs.append((alone(one), alone(replace(one, **{field: getattr(donor, field)}))))
    for first, second in pairs:
        assert first == second or print_module(first) != print_module(second)


def test_the_valid_strategy_has_an_entry_for_every_instruction_class() -> None:
    assert set(TYPED) == set(get_args(Instr))


@given(st.lists(st.booleans().flatmap(valid_modules), min_size=1, max_size=8))
def test_every_valid_module_assembles_and_validates_in_both_engines(
    wasm_tools: Tools, modules: list[Module]
) -> None:
    """[law: prints-and-validates] Every module the valid strategy draws, closed or not, prints
    to WAT that wast2json assembles, that wabt validates, and that wasmtime compiles as a
    `module definition`: a batch of them, each claimed valid, meets no disagreement."""
    items: list[Item] = [Verdict(print_module(module), valid=True) for module in modules]
    texts = "\n".join(item.module for item in items)
    for report in (run_wabt(wasm_tools, items), run_wasmtime(wasm_tools, items)):
        assert report.wrong == (), f"{report.output}\n{texts}"
