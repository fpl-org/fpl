"""Typed dispatch (design 09): the type words, the types of an effect's slots and the words of
a definition's clauses."""

from dataclasses import fields

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fpl.ast_core import Call, Define, Effect, Listed, Push, Quotation, Run, Strand
from fpl.desugar import desugar, resugar
from fpl.driver import run
from fpl.errors import FplError, Span
from fpl.eval import BUILTINS, effect_line, evaluate
from fpl.parse import parse
from fpl.types import Arrow, Kind, elaborate

TYPES = ("Int", "Decimal", "Text", "Symbol")
ATOMS = [
    ("1", "Int"),
    ("-9", "Int"),
    ("1.5", "Decimal"),
    ("0.0", "Decimal"),
    ("“a”", "Text"),
]
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


HERE = Span(1, 1)
LINE = Effect((), ("y",))
WORDS: dict[tuple[int, ...], str] = {
    (): "f",
    (1,): "f/1",
    (2,): "f/2",
    (1, 1): "f/1/1",
    (1, 2): "f/1/2",
    (2, 1): "f/2/1",
}
QUERIES = ("", "/history", "/doc", "/effect")


@given(st.lists(st.sampled_from(list(WORDS)), min_size=1, max_size=4, unique=True))
def test_a_definition_is_called_and_queried_at_its_word(
    clauses: list[tuple[int, ...]],
) -> None:
    """[law: clause-word] a definition's word is its name when `clause == ()`, `name/n/i` for
    clause i of arity n and `name/n` for the arity-n dispatcher; eval's words, types' arrows and
    the queries `history`, `doc` and `effect` key on `Define.word`, so a hand-built clause is
    called and queried at its path, and a definition with `clause == ()` behaves as before."""
    defines = [
        define
        for clause in clauses
        for define in (
            Define("f", LINE, (Push(0),), clause=clause),
            Define("f", LINE, (Push(WORDS[clause]),), WORDS[clause], clause=clause),
        )
    ]
    runs = [Run((Call(WORDS[clause] + query, HERE),)) for clause in clauses for query in QUERIES]
    stacks = iter(evaluate((*defines, *runs)))
    arrows, _ = elaborate((*defines, *runs))
    for clause in clauses:
        word = WORDS[clause]
        assert [next(stacks) for _ in QUERIES] == [
            (word,),
            (Listed((Quotation((Push(0),)),)),),
            (word,),
            (Listed(("--", "y")),),
        ]
        assert arrows[word] == Arrow((), (Kind.TEXT,))
        assert defines[-1].word == WORDS[clauses[-1]]
        assert Define("f", LINE, (), clause=clause).paths == tuple(
            WORDS[clause[:end]] for end in range(len(clause) + 1)
        )


def test_a_clause_is_named_by_its_word_and_a_dispatcher_lists_its_clauses() -> None:
    """[law: clause-word] a clause's refusal names it by its word; a dispatcher carries its
    clauses' words in order."""
    with pytest.raises(FplError, match=r"^ERROR: 1:1 f/1/1 leaves 0 values, its effect line 1$"):
        elaborate((Define("f", LINE, (), clause=(1, 1)),))
    dispatcher = Define("f", LINE, (), clause=(1,), clauses=("f/1/1", "f/1/2"))
    assert (dispatcher.word, dispatcher.clauses) == ("f/1", ("f/1/1", "f/1/2"))
    assert Define("f", LINE, ()).clauses == ()


PARTS = (None, "Int", "Text", "one")


@given(st.lists(st.sampled_from(PARTS), max_size=3))
def test_a_typed_slot_is_written_back_as_written(parts: list[str | None]) -> None:
    """[law: typed-read] `x: T` on an effect line is a value slot of type T and is written back
    as `x: T`; resugar after desugar gives the source back for untyped and value-typed heads."""
    slots = [f"a{i}" if part is None else f"a{i}: {part}" for i, part in enumerate(parts)]
    source = f"f : {' '.join([*slots, '--'])}\n"
    (define,) = desugar(parse(source))
    assert isinstance(define, Define)
    assert define.effect.types == tuple(parts)
    assert define.effect.slots == ("value",) * len(parts)
    assert resugar((define,)) == parse(source)
    assert effect_line(define) == Listed((*" ".join(slots).replace(": ", ": ").split(), "--"))


@given(st.lists(st.sampled_from(["a", "bc: Int", "t: [ ]"]), max_size=2), st.booleans())
def test_a_guard_or_compound_type_on_an_effect_line_is_refused(
    before: list[str], guard: bool
) -> None:
    """[law: head-refusals] `∈` on an effect line and a compound type `x: ⟨ … ⟩` are refused as
    unimplemented, at the source's start as every unimplemented construct is (hole
    unimplemented-words)."""
    prefix = " ".join(["f", ":", *before, "x ∈" if guard else "x: ⟨"])
    source = f"{prefix} Int{'' if guard else ' ⟩'} -- y\n"
    with pytest.raises(FplError, match=r"^ERROR: 1:1 no evaluator yet$"):
        desugar(parse(source))


LONE = "f : x: Int -- y\n\tdrop #int\n"


def test_a_second_typed_clause_of_one_arity_is_refused() -> None:
    """[S49] Pinned until clauses of one arity are ordered: `f : x: Int` beside `f : x: Text`
    is refused as unimplemented."""
    with pytest.raises(FplError, match=r"^ERROR: 1:1 no evaluator yet$"):
        run(LONE + "f : x: Text -- y\n\tdrop #text\n5 f\n")


def test_a_lone_typed_clause_runs_its_body_on_any_value() -> None:
    """[S49] Pinned until a typed clause is guarded: a lone `f : x: Int -- y` runs its body on
    a text."""
    assert run(LONE + "“a” f\n5 f\n") == "#int\n#int\n"


def test_a_guard_with_no_row_for_its_value_is_an_error() -> None:
    """[S49] Pinned until a failing guard is a miss: a match row guarded by `p`, whose match has
    no row for 5, stops with `no row matches` from inside `p`."""
    source = "p : x -- b\n\tmatch\n\t\t0\t1\nf : x -- y\n\tmatch\n\t\t( _ ∈ p )\t#p\n\t\t_\t#any\n"
    with pytest.raises(FplError, match=r"^ERROR: 2:2 no row matches$"):
        run(source + "5 f\n")
