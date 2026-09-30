"""Typed dispatch (design 09): the type words and the types of an effect's slots."""

from dataclasses import fields

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fpl.ast_core import Effect, Strand
from fpl.driver import run
from fpl.errors import Span
from fpl.eval import BUILTINS

TYPES = ("Int", "Decimal", "Text", "Symbol")
ATOMS = [("1", "Int"), ("-9", "Int"), ("1.5", "Decimal"), ("0.0", "Decimal"), ("“a”", "Text")]
atoms = st.sampled_from(ATOMS)


@given(st.sampled_from([*ATOMS, ("#a", "Symbol")]), st.sampled_from(TYPES))
def test_a_type_word_leaves_1_on_a_value_of_its_type_and_0_on_any_other(
    literal: tuple[str, str], word: str
) -> None:
    """[law: type-word] each of the builtins `Int Decimal Text Symbol : x -- b` leaves 1 on a
    value of its type and 0 on every other value."""
    written, kind = literal
    assert run(f"{written} {word}\n") == f"{int(kind == word)}\n"


@given(st.lists(atoms, min_size=2, max_size=4), st.sampled_from(TYPES))
def test_a_strand_has_its_items_type_when_they_share_one(
    items: list[tuple[str, str]], word: str
) -> None:
    """[law: type-word] a strand has its items' type when they all share one; a mixed strand has
    no type word, so every type word leaves 0 on it."""
    written = " ".join(text for text, _ in items)
    shared = all(kind == word for _, kind in items)
    assert run(f"{written} {word}\n") == f"{int(shared)}\n"


def test_a_mixed_or_empty_strand_is_of_no_type() -> None:
    """[law: type-word] `1 “a” Int` and `1 “a” Text` both print 0; an empty strand, which no
    source builds, is of no type either."""
    assert run("1 “a” Int\n1 “a” Text\n") == "0\n0\n"
    assert {BUILTINS[word](Span(1, 1), Strand(())) for word in TYPES} == {(0,)}


@given(
    st.lists(st.sampled_from(["x", "y", "q"]), max_size=3),
    st.lists(st.sampled_from([None, "Int", "one"]), max_size=3),
)
def test_an_effect_has_one_type_per_input(ins: list[str], types: list[str | None]) -> None:
    """[law: effect-types] `Effect` has one type part per input (`None` when untyped) in
    `types`, keyword-only after `fails` beside `slots`, filled as `slots` is; a count other than
    one per input is refused."""
    assert [(f.name, f.kw_only) for f in fields(Effect)][2:] == [
        ("fails", False),
        ("slots", True),
        ("types", True),
    ]
    if types and len(types) != len(ins):
        with pytest.raises(ValueError, match=r"^one type per input$"):
            Effect(tuple(ins), (), types=tuple(types))
    else:
        effect = Effect(tuple(ins), (), types=tuple(types))
        assert effect.types == (tuple(types) or (None,) * len(ins))
        assert effect.slots == ("value",) * len(ins)
