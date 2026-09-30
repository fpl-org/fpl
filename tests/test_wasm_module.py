"""The fields of fpl.asm.wasm's module, and the one limit that is the module's own."""

from collections.abc import Iterable
from collections.abc import Set as AbstractSet
from dataclasses import fields
from typing import Any, cast, get_args

import pytest
from hypothesis import given
from hypothesis import strategies as st
from wasm_strategies import DESCS, FIELDS, INSTRS

from fpl.asm.wasm.instr import (
    Binop,
    Const,
    Cvtop,
    IBinop,
    ICvtop,
    Instr,
    IRelop,
    ITestop,
    IUnop,
    Load,
    MemArg,
    PackSize,
    Relop,
    Sign,
    Store,
    Unop,
)
from fpl.asm.wasm.instr import Testop as _Testop  # pytest would collect a Test* name
from fpl.asm.wasm.module import (
    Data,
    Elem,
    ExternKind,
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
from fpl.asm.wasm.types import GlobalType, Limits, MemType, NumType, TableType

memory = MemType(Limits(1, None))


@given(st.integers(min_value=0, max_value=2), st.integers(min_value=0, max_value=2))
def test_a_module_holds_at_most_one_memory_counting_imports(defined: int, imported: int) -> None:
    mems = (Mem(memory),) * defined
    imports = (Import("m", "mem", MemImport(memory)),) * imported
    if defined + imported <= 1:
        assert (Module(imports=imports, mems=mems).mems, len(imports)) == (
            mems,
            imported,
        )
    else:
        with pytest.raises(ValueError, match=r"^a module holds at most one memory"):
            Module(imports=imports, mems=mems)


@given(
    st.integers(min_value=0, max_value=2**32 - 1),
    st.binary(max_size=4),
    st.text(max_size=4),
)
def test_a_module_field_is_its_parts(x: int, init: bytes, name: str) -> None:
    table, glob, offset = (
        TableType(Limits(x, x)),
        GlobalType(True, "i64"),
        (Const("i32", 0),),
    )
    imports = tuple(
        Import("m", name, d)
        for d in (
            FuncImport(x),
            TableImport(table),
            MemImport(memory),
            GlobalImport(glob),
        )
    )
    g, data, elem = Global(glob, offset), Data(offset, init), Elem(x, offset, (x,))
    module = Module(
        imports=imports,
        globals=(g,),
        tables=(Table(table),),
        datas=(data,),
        elems=(elem,),
        start=x,
    )
    assert [(i.module, i.name, i.desc.type) for i in imports[2:]] == [
        ("m", name, memory), ("m", name, glob)
    ]  # fmt: skip
    assert (g.type, g.init, data.offset, data.init) == (glob, offset, offset, init)
    assert (elem.table, elem.offset, elem.funcs) == (x, offset, (x,))
    assert (module.globals, module.datas, module.elems, module.start) == (
        (g,),
        (data,),
        (elem,),
        x,
    )
    assert module.tables[0].type == table
    load, store = Load("i64", MemArg(3, x), (32, "u")), Store("i32", MemArg(0, x), 8)
    assert (load.arg, load.pack) == (MemArg(3, x), (32, "u"))
    assert (store.arg, store.size) == (MemArg(0, x), 8)


def sampled(strategy: st.SearchStrategy[Any]) -> list[Any]:
    """Every element of every `sampled_from` inside `strategy`: the domain it draws from, found
    by walking the objects Hypothesis 6.168 builds (a sampled_from keeps `elements`; builds,
    lists and map keep their parts as attributes; a lazy strategy its `wrapped_strategy`).
    Not for a strategy that holds itself (`instrs`, `exprs`): the walk has no cycle guard."""
    found: list[Any] = []
    todo: list[object] = [strategy]
    while todo:
        node = todo.pop()
        if isinstance(node, tuple | list):
            todo.extend(cast("Iterable[object]", node))
        elif isinstance(node, dict):
            todo.extend(cast("dict[object, object]", node).values())
        elif isinstance(node, st.SearchStrategy):
            found.extend(vars(node).get("elements", ()))
            lazy = cast("object", node)
            todo.extend([*vars(node).values(), getattr(lazy, "wrapped_strategy", None)])
    return found


@given(st.data())
def test_the_structural_strategy_draws_every_class_field_and_operator(
    data: st.DataObject,
) -> None:
    """[law: strategy-total] The structural strategy's table covers exactly `get_args(Instr)`
    and every module field, and every operator Literal occurs in its sub-strategies: each
    table's keys equal the model's, each Literal's values equal those the table's own
    strategies sample (not an enumeration beside them), and a drawn class's builder draws an
    instance of exactly that class."""
    assert INSTRS.keys() == set(get_args(Instr))
    assert DESCS.keys() == set(get_args(ImportDesc))
    assert FIELDS.keys() == {f.name for f in fields(Module)}
    unops, binops, testops, relops, cvtops, loads, stores = (
        sampled(INSTRS[cls]) for cls in (Unop, Binop, _Testop, Relop, Cvtop, Load, Store)
    )
    packs = [load.pack for load in loads if load.pack is not None]
    occurring: list[tuple[object, AbstractSet[object]]] = [
        (IUnop, {x.op for x in unops}),
        (IBinop, {x.op for x in binops}),
        (ITestop, {x.op for x in testops}),
        (IRelop, {x.op for x in relops}),
        (ICvtop, {x.op for x in cvtops}),
        (
            NumType,
            {x.type for x in unops} | {x.type for x in loads} | {x.type for x in stores},
        ),
        (PackSize, {size for size, _ in packs} | {x.size for x in stores} - {None}),
        (Sign, {sign for _, sign in packs}),
        (ExternKind, set(sampled(FIELDS["exports"]))),
    ]
    for literal, values in occurring:
        assert values == set(get_args(literal)), literal
    cls = data.draw(st.sampled_from(get_args(Instr)))
    assert type(data.draw(INSTRS[cls])) is cls
    kind = data.draw(st.sampled_from(get_args(ImportDesc)))
    assert type(data.draw(DESCS[kind])) is kind
