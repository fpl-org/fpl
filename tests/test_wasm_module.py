"""The fields of fpl.asm.wasm's module, and the one limit that is the module's own."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fpl.asm.wasm.instr import Const, Load, MemArg, Store
from fpl.asm.wasm.module import (
    Data,
    Elem,
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
from fpl.asm.wasm.types import GlobalType, Limits, MemType, TableType

memory = MemType(Limits(1, None))


@given(st.integers(min_value=0, max_value=2), st.integers(min_value=0, max_value=2))
def test_a_module_holds_at_most_one_memory_counting_imports(defined: int, imported: int) -> None:
    mems = (Mem(memory),) * defined
    imports = (Import("m", "mem", MemImport(memory)),) * imported
    if defined + imported <= 1:
        assert (Module(imports=imports, mems=mems).mems, len(imports)) == (mems, imported)
    else:
        with pytest.raises(ValueError, match="at most one memory"):
            Module(imports=imports, mems=mems)


@given(st.integers(min_value=0, max_value=2**32 - 1), st.binary(max_size=4), st.text(max_size=4))
def test_a_module_field_is_its_parts(x: int, init: bytes, name: str) -> None:
    table, glob, offset = TableType(Limits(x, x)), GlobalType(True, "i64"), (Const("i32", 0),)
    imports = tuple(
        Import("m", name, d)
        for d in (FuncImport(x), TableImport(table), MemImport(memory), GlobalImport(glob))
    )
    g, data, elem = Global(glob, offset), Data(offset, init), Elem(x, offset, (x,))
    module = Module(
        imports=imports, globals=(g,), tables=(Table(table),), datas=(data,), elems=(elem,), start=x
    )
    assert [(i.module, i.name, i.desc.type) for i in imports[2:]] == [
        ("m", name, memory), ("m", name, glob)
    ]  # fmt: skip
    assert (g.type, g.init, data.offset, data.init) == (glob, offset, offset, init)
    assert (elem.table, elem.offset, elem.funcs) == (x, offset, (x,))
    assert (module.globals, module.datas, module.elems, module.start) == ((g,), (data,), (elem,), x)
    assert module.tables[0].type == table
    load, store = Load("i64", MemArg(3, x), (32, "u")), Store("i32", MemArg(0, x), 8)
    assert (load.arg, load.pack) == (MemArg(3, x), (32, "u"))
    assert (store.arg, store.size) == (MemArg(0, x), 8)
