"""The checker of fpl.asm.wasm: the stack-polymorphic cases, the valid strategy, the invalid
catalogue, and agreement with wabt and wasmtime."""

from dataclasses import replace
from typing import get_args

from hypothesis import given
from hypothesis import strategies as st
from wasm_oracle import Item, Tools, Verdict, run_wabt, run_wasmtime
from wasm_strategies import CATALOGUE, invalid_modules, valid_modules

from fpl.asm.wasm.instr import (
    Binop,
    Block,
    Br,
    BrIf,
    BrTable,
    Call,
    CallIndirect,
    Const,
    Drop,
    GlobalGet,
    GlobalSet,
    If,
    Instr,
    Load,
    LocalGet,
    LocalSet,
    LocalTee,
    MemArg,
    MemorySize,
    Nop,
    ReturnCall,
    ReturnCallIndirect,
    Select,
    Store,
    Unreachable,
)
from fpl.asm.wasm.module import (
    Data,
    Elem,
    Export,
    Func,
    Global,
    GlobalImport,
    Import,
    Mem,
    Module,
    Table,
)
from fpl.asm.wasm.text import print_module
from fpl.asm.wasm.types import FuncType, GlobalType, Limits, MemType, TableType, TypeUse, ValType
from fpl.asm.wasm.valid import Invalid, InvalidKind, check


def func_of(results: tuple[ValType, ...], *body: Instr) -> Module:
    """A module whose one function, of type [] -> results, has `body`."""
    return Module(types=(FuncType((), results),), funcs=(Func(0, (), body),))


def memory_of(limits: Limits) -> Module:
    return Module(mems=(Mem(MemType(limits)),))


IMPORTED = Import("a", "b", GlobalImport(GlobalType(True, "i32")))
ZERO = Const("i32", 0)
WIDE = Const("i64", 0)
I32 = GlobalType(False, "i32")
READ = Global(I32, (GlobalGet(0),))
POLYMORPHIC = (Block("i64", (Unreachable(), BrTable((0,), 1))), Drop(), Const("i32", 0))

INDIRECT = (ZERO, CallIndirect(0, TypeUse(0)), Drop(), ZERO, ReturnCallIndirect(0, TypeUse(0)))
STORED = (ZERO, ZERO, Store("i32", MemArg(2, 0), None))
ACCESSES = Module(
    types=(FuncType((), ("i32",)),),
    mems=(Mem(MemType(Limits(1, None))),),
    tables=(Table(TableType(Limits(1, None))),),
    funcs=(Func(0, (), (*STORED, *INDIRECT)),),
)
"""A store and both indirect calls, which a valid strategy's short run may not draw."""

AGREED: list[tuple[Module, Invalid | None]] = [
    (ACCESSES, None),
    (func_of(("i32",), Unreachable(), Binop("i32", "add")), None),
    (func_of(("i32",), Unreachable(), WIDE, Binop("i32", "add")), Invalid("mismatch", (0, 2))),
    (func_of(("i64",), Unreachable(), ZERO, Select(None)), None),
    (func_of(("i32",), Unreachable(), WIDE, ZERO, Select(None)), Invalid("mismatch", (0,))),
    (func_of(("i32",), Block("i32", POLYMORPHIC)), None),
    (func_of((), ZERO, WIDE, ZERO, Select(None), Drop()), Invalid("mismatch", (0, 3))),
    (func_of(("i64",), Const("i64", 1), Const("i64", 2), ZERO, Select(("i64",))), None),
    (func_of((), ZERO, ZERO, ZERO, Select(("i32", "i32")), Drop()), Invalid("mismatch", (0, 3))),
    (Module(imports=(IMPORTED,), globals=(READ,)), Invalid("const", (0, 0))),
    (Module(globals=(Global(I32, (ZERO,)), READ)), Invalid("const", (1, 0))),
    (Module(globals=(Global(I32, ()),)), Invalid("underflow", (0,))),
    (memory_of(Limits(65536, 65536)), None),
    (memory_of(Limits(65537, None)), Invalid("limits", (0,))),
    (memory_of(Limits(0, 65537)), Invalid("limits", (0,))),
]
"""Fixed cases on which the checker, wabt and wasmtime agree: the stack-polymorphic ones after
`unreachable` (probe verdict.wast), select's arity, constant expressions and memory limits."""

SPEC_ONLY: list[tuple[Module, Invalid | None]] = [
    (func_of((), Block(TypeUse(1), ())), Invalid("type", (0, 0))),
    (func_of((), ZERO, ZERO, ZERO, Select(()), Drop()), Invalid("mismatch", (0, 3))),
    (Module(tables=(Table(TableType(Limits(0, 2**32 - 1))),)), None),
    (Module(tables=(Table(TableType(Limits(2**32, None))),)), Invalid("limits", (0,))),
]
"""Fixed cases where wabt 1.0.41 leaves Release 3.0 (HOLES.md oracle-feature-set), or whose
numbers do not print as a table's u32 limits."""

EMPTY = FuncType((), ())
UNARY = FuncType(("i32",), ("i32",))
ONE = Module(types=(EMPTY,), funcs=(Func(0, (), ()),))
MEMORY = (Mem(MemType(Limits(1, None))),)
TABLES = (Table(TableType(Limits(1, None))),)
FIXED = Import("a", "b", GlobalImport(GlobalType(False, "i32")))

SITES: list[tuple[Module, Invalid | None]] = [
    (func_of((), ZERO, Load("i32", MemArg(2, 0), None), Drop()), Invalid("memory", (0, 1))),
    (
        replace(func_of((), ZERO, Load("i64", MemArg(1, 0), (8, "u")), Drop()), mems=MEMORY),
        Invalid("align", (0, 1)),
    ),
    (replace(func_of(("i64",), GlobalGet(0)), imports=(IMPORTED,)), Invalid("mismatch", (0,))),
    (replace(func_of(("i64",), MemorySize()), mems=MEMORY), Invalid("mismatch", (0,))),
    (func_of(("i32",), MemorySize()), Invalid("memory", (0, 0))),
    (replace(func_of((), ZERO, GlobalSet(0)), imports=(FIXED,)), Invalid("immutable", (0, 1))),
    (func_of((), ZERO, GlobalSet(0)), Invalid("global", (0, 1))),
    (func_of((), GlobalGet(0), Drop()), Invalid("global", (0, 0))),
    (func_of((), ZERO, CallIndirect(0, TypeUse(0))), Invalid("table", (0, 1))),
    (replace(func_of((), ZERO, Block(TypeUse(1), ()), Drop()), types=(EMPTY, UNARY)), None),
    (func_of((), LocalGet(0), Drop()), Invalid("local", (0, 0))),
    (func_of((), ZERO, LocalSet(0)), Invalid("local", (0, 1))),
    (func_of((), ZERO, LocalTee(0), Drop()), Invalid("local", (0, 1))),
    (func_of((), Call(1)), Invalid("func", (0, 0))),
    (func_of((), ReturnCall(1)), Invalid("func", (0, 0))),
    (
        Module(
            types=(FuncType((), ("i32",)), EMPTY),
            funcs=(Func(0, (), (ReturnCall(1),)), Func(1, (), ())),
        ),
        Invalid("tail-result", (0, 0)),
    ),
    (
        replace(func_of((), ZERO, CallIndirect(0, TypeUse(1))), tables=TABLES),
        Invalid("type", (0, 1)),
    ),
    (func_of((), Br(1)), Invalid("label", (0, 0))),
    (func_of((), ZERO), Invalid("leftover", (0,))),
    (
        func_of((), Block("i32", (Block(None, (ZERO, ZERO, BrTable((1,), 0))), ZERO)), Drop()),
        Invalid("br-table-arity", (0, 0, 0, 2)),
    ),
    (func_of((), ZERO, If(None, (Nop(),), (Nop(), Drop()))), Invalid("underflow", (0, 1, 2))),
    (replace(func_of((), ZERO, ZERO, If(TypeUse(1), (), ()), Drop()), types=(EMPTY, UNARY)), None),
    (Module(globals=(Global(I32, (LocalGet(0),)),)), Invalid("const", (0, 0))),
    (Module(datas=(Data((ZERO,), b""),)), Invalid("memory", (0,))),
    (Module(mems=MEMORY, datas=(Data((WIDE,), b""),)), Invalid("mismatch", (0,))),
    (Module(imports=(FIXED,), mems=MEMORY, datas=(Data((GlobalGet(0),), b""),)), None),
    (replace(ONE, elems=(Elem(0, (ZERO,), (0,)),)), Invalid("table", (0,))),
    (replace(ONE, tables=TABLES, elems=(Elem(0, (ZERO,), (1,)),)), Invalid("func", (0,))),
    (replace(ONE, tables=TABLES, elems=(Elem(0, (WIDE,), (0,)),)), Invalid("mismatch", (0,))),
    (replace(ONE, imports=(FIXED,), tables=TABLES, elems=(Elem(0, (GlobalGet(0),), (0,)),)), None),
    (replace(ONE, exports=(Export("f", "func", 1),)), Invalid("func", (0,))),
    (
        replace(ONE, exports=(Export("f", "func", 0), Export("f", "func", 0))),
        Invalid("export-name", (1,)),
    ),
    (replace(ONE, start=1), Invalid("func", ())),
    (replace(ONE, start=0), None),
    (replace(func_of(("i32",), ZERO), start=0), Invalid("start", ())),
    (func_of(("i32",), ZERO, Br(0)), None),
    (func_of(("i32",), ZERO, ZERO, BrIf(0)), None),
    (replace(func_of(("i32",)), funcs=(Func(0, ("i32",), (ZERO, LocalTee(0))),)), None),
    (Module(types=(EMPTY,), funcs=(Func(1, (), ()),)), Invalid("type", (0,))),
]
"""One fixed case per refusal site whose kind and place no property pins: memory accesses,
the index spaces, `leftover`, `br-table-arity`, a typed `if`, an error in an `else` arm, and
the data, element, export and start fields, a block that takes a parameter and a br that
carries one."""


def test_the_checker_decides_the_fixed_cases_as_the_spec_does() -> None:
    for module, verdict in AGREED + SPEC_ONLY + SITES:
        assert check(module) == verdict, print_module(module)


def test_wabt_and_wasmtime_decide_the_agreed_cases_alike(wasm_tools: Tools) -> None:
    items: list[Item] = [Verdict(print_module(m), valid=v is None) for m, v in AGREED]
    for report in (run_wabt(wasm_tools, items), run_wasmtime(wasm_tools, items)):
        assert report.wrong == (), report.output


@given(st.booleans().flatmap(valid_modules))
def test_the_checker_accepts_every_valid_module(module: Module) -> None:
    """[law: checker-accepts-valid] The checker accepts every module the valid strategy draws,
    closed or not."""
    assert check(module) is None, print_module(module)


def test_the_catalogue_has_one_mutation_per_kind() -> None:
    assert set(CATALOGUE) == set(get_args(InvalidKind))


@given(invalid_modules())
def test_each_mutation_is_refused_with_its_kind(case: tuple[InvalidKind, Module]) -> None:
    """[law: invalid-kind-exact] Each catalogue mutation of a drawn valid module makes the
    checker return `Invalid` of exactly that mutation's kind."""
    kind, module = case
    verdict = check(module)
    assert verdict is not None, print_module(module)
    assert verdict.kind == kind, print_module(module)


verdict_modules = st.booleans().flatmap(valid_modules) | invalid_modules().map(lambda c: c[1])


@given(st.lists(verdict_modules, min_size=1, max_size=8))
def test_the_checker_agrees_with_wabt_and_wasmtime(
    wasm_tools: Tools, modules: list[Module]
) -> None:
    """[law: checker-agrees] On a batch mixing valid modules and catalogue mutations, the
    checker's verdict on every module equals wabt's (assert_invalid) and wasmtime's (a module
    definition if the checker accepts it, assert_invalid if not)."""
    items: list[Item] = [Verdict(print_module(m), valid=check(m) is None) for m in modules]
    texts = "\n".join(item.module for item in items)
    for report in (run_wabt(wasm_tools, items), run_wasmtime(wasm_tools, items)):
        assert report.wrong == (), f"{report.output}\n{texts}"
