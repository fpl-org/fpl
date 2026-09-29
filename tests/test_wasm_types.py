"""The types of fpl.asm.wasm are structural values, and the bit widths are the types' own."""

import dataclasses
from typing import get_args

import pytest
from hypothesis import given
from hypothesis import strategies as st

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
)

numtypes = st.sampled_from(get_args(NumType))
valtypes = st.lists(numtypes, max_size=4).map(tuple)
sizes = st.integers(min_value=0, max_value=2**32)


@given(valtypes, valtypes, sizes, st.none() | sizes, st.booleans())
def test_a_type_is_its_fields(
    params: tuple[NumType, ...],
    results: tuple[NumType, ...],
    low: int,
    high: int | None,
    mutable: bool,
) -> None:
    t = params[0] if params else "i32"
    f, lim, g, use = (
        FuncType(params, results),
        Limits(low, high),
        GlobalType(mutable, t),
        TypeUse(low),
    )
    block: BlockType = use
    assert (f.params, f.results, lim.min, lim.max, use.index) == (params, results, low, high, low)
    assert (g.mutable, g.type, block, MemType(lim).limits, TableType(lim).limits) == (
        mutable,
        t,
        TypeUse(low),
        lim,
        lim,
    )
    for value in (f, lim, MemType(lim), TableType(lim), g, use):
        copy = dataclasses.replace(value)
        assert (copy, hash(copy)) == (value, hash(value))
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(value, dataclasses.fields(value)[0].name, None)


@given(numtypes)
def test_the_width_of_a_number_type_is_in_its_name(t: NumType) -> None:
    assert WIDTH[t] == int(t[1:])
    assert set(WIDTH) == set(get_args(NumType))
