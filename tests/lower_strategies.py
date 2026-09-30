"""Walker values and walker programs for the lowering's properties (design section 7)."""

from decimal import Decimal

from hypothesis import strategies as st

from fpl.ast_core import Call, Dict, Listed, Push, Quotation, Strand, Symbol, Value
from fpl.errors import Span

NAMES = st.sampled_from(("a", "b", "k", "dup", "x"))
atoms: st.SearchStrategy[int | Decimal | str] = st.one_of(
    st.integers(-5, 5),
    st.decimals(-5, 5, places=1, allow_nan=False, allow_infinity=False),
    st.text("xyz", max_size=2),
)


def _compound(children: st.SearchStrategy[Value]) -> st.SearchStrategy[Value]:
    code = st.lists(st.one_of(children.map(Push), NAMES.map(lambda n: Call(n, Span(1, 1)))))
    return st.one_of(
        st.lists(children, max_size=3).map(lambda xs: Listed(tuple(xs))),
        code.map(lambda c: Quotation(tuple(c))),
        st.lists(st.tuples(NAMES, children), max_size=2).map(lambda es: Dict(tuple(es))),
    )


def walker_values() -> st.SearchStrategy[Value]:
    """Walker values at every sort: atoms, strands, symbols, and lists, quotations and dicts
    holding any of them."""
    leaves = st.one_of(
        atoms,
        st.lists(atoms, min_size=2, max_size=3).map(lambda xs: Strand(tuple(xs))),
        NAMES.map(Symbol),
    )
    return st.recursive(leaves, _compound, max_leaves=6)
