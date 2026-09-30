"""Typed dispatch (design 09): the type words, the types of an effect's slots and the words of
a definition's clauses."""

from collections.abc import Iterator
from dataclasses import fields, replace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fpl.ast_core import (
    Bind,
    Call,
    Define,
    Effect,
    Guarded,
    Listed,
    Match,
    Node,
    Push,
    Quotation,
    Row,
    Run,
    Strand,
    Value,
    Var,
)
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
    statements = desugar(parse("one : x -- b\n\tdrop 1\n" + source))
    define = next(s for s in statements if isinstance(s, Define) and s.name == "f")
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


def test_a_lone_typed_clause_is_guarded() -> None:
    """[law: no-clause-fails] a lone `f : x: Int -- y` fails on `“a” f` with `no row matches`
    at its head, and runs its body on 5."""
    assert run(LONE + "5 f\n") == "#int\n"
    with pytest.raises(FplError, match=r"^ERROR: 1:1 no row matches$"):
        run(LONE + "“a” f\n")


def test_a_guard_with_no_row_for_its_value_is_an_error() -> None:
    """[S49] Pinned until a failing guard is a miss: a match row guarded by `p`, whose match has
    no row for 5, stops with `no row matches` from inside `p`."""
    source = "p : x -- b\n\tmatch\n\t\t0\t1\nf : x -- y\n\tmatch\n\t\t( _ ∈ p )\t#p\n\t\t_\t#any\n"
    with pytest.raises(FplError, match=r"^ERROR: 2:2 no row matches$"):
        run(source + "5 f\n")


def clauses(groups: set[int], part: str | None = None) -> str:
    """One clause per arity, the largest first, its first slot of type part, its body leaving
    its arity."""
    lines: list[str] = []
    for n in sorted(groups, reverse=True):
        slots = [f"x{i}" for i in range(n)]
        if part is not None:
            slots[0] = f"x0: {part}"
        lines.append(f"f : {' '.join(slots)} -- y\n\t;; c{n}\n\t{'drop ' * n}{n}\n")
    return "".join(lines)


def called(code: tuple[Node, ...]) -> Iterator[str]:
    """The words code calls, in quotations and binders too."""
    for node in code:
        if isinstance(node, Call):
            yield node.name
        elif isinstance(node, Bind):
            yield from called(node.body)
        elif isinstance(node, Push) and isinstance(node.value, Quotation):
            yield from called(node.value.code)


def top(source: str) -> Value:
    """The top of the stack the last line leaves."""
    return evaluate(desugar(parse(source)))[-1][-1]


GROUPS = st.sets(st.sampled_from([1, 2, 3]), min_size=1)


@given(GROUPS, st.integers(1, 3), st.booleans())
def test_the_balance_picks_the_arity_group(groups: set[int], balance: int, block: bool) -> None:
    """[law: arity-choice] the balance at a call selects the arity group, the largest arity that
    saturates else the smallest, at every dispatch site and in `inputs` by child count."""
    fits = [n for n in groups if n <= balance]
    chosen = max(fits) if fits else min(groups)
    line = "f\n" + "\t1\n" * balance if block else " | ".join(["1"] * balance) + " f\n"
    source = clauses(groups) + line
    *_, last = desugar(parse(source))
    assert isinstance(last, Run)
    word = f"f/{chosen}" if len(groups) > 1 else "f"
    assert [name for name in called(last.code) if name.startswith("f")] == [word]
    if chosen == balance or (chosen < balance and not block):
        assert run(source) == run(" | ".join([*["1"] * (balance - chosen), str(chosen)]) + "\n")


P4 = "f : x y -- z\n\t+\nf : x -- y\n\t1 +\n"


def test_p4_takes_its_group_by_the_balance() -> None:
    """[law: arity-choice] `5 f` takes f/1, `1 | 2 f` takes f/2, and `1 2 f` is one strand."""
    assert run(P4 + "5 f\n1 | 2 f\n1 2 f\n") == "6\n3\n2 3\n"


@given(GROUPS, st.sampled_from([None, "Int", "Text"]))
def test_a_dispatched_word_has_a_path_per_group_and_clause(
    groups: set[int], part: str | None
) -> None:
    """[law: clause-path] a word is dispatched when it has two or more distinct keys, or one key
    with a typed position; `f/n/i/effect` is the clause's line as written, `f/n/effect` the
    dispatcher's, `doc` and `history` at `f/n` answer for the group's clause; a query at `f`
    answers as at `f/n` when the word has one group and is refused naming its groups
    otherwise."""
    source = clauses(groups, part)
    if len(groups) == 1 and part is None:
        with pytest.raises(FplError, match=r"^ERROR: 1:1 no evaluator yet$"):
            desugar(parse(source + f"f/{min(groups)}/effect\n"))
        return
    for n in groups:
        first = ("x0",) if part is None else ("x0:", part)
        ins = (*first, *(f"x{i}" for i in range(1, n)))
        line = Listed((*ins, "--", "y"))
        fails = Listed((*line.items, "+fail")) if part else line
        assert top(source + f"f/{n}/1/effect\n") == line
        assert top(source + f"f/{n}/effect\n") == fails
        assert top(source + f"f/{n}/doc\n") == top(source + f"f/{n}/1/doc\n") == f"c{n}"
        assert top(source + f"f/{n}/history\n") == Listed(())
    if len(groups) == 1:
        assert top(source + "f/effect\n") == top(source + f"f/{min(groups)}/effect\n")
        return
    names = " ".join(f"f/{n}" for n in sorted(groups))
    at = source.count("\n") + 1
    refusal = rf"^ERROR: {at}:1 f/effect names more than one group: {names}$"
    with pytest.raises(FplError, match=refusal):
        desugar(parse(source + "f/effect\n"))


def test_p4_has_its_paths() -> None:
    """[law: clause-path] P4's paths are `f/1 f/1/1 f/2 f/2/1`, and `f/effect` is refused
    naming `f/1 f/2`."""
    defines = [s for s in desugar(parse(P4)) if isinstance(s, Define)]
    assert sorted(d.word for d in defines) == ["f/1", "f/1/1", "f/2", "f/2/1"]
    with pytest.raises(FplError, match=r"^ERROR: 5:1 f/effect names more than one group: f/1 f/2$"):
        run(P4 + "f/effect\n")


@given(st.integers(0, 2), st.integers(1, 3))
def test_redefining_one_untyped_key_leaves_a_word_undispatched(arity: int, times: int) -> None:
    """[law: single-clause] a word whose definitions all have one key with no typed position,
    however often that key is redefined, is not dispatched: no dispatcher, no Match,
    `clause == ()`, the same paths and queries."""
    head = f"f : {' '.join([*(f'x{i}' for i in range(arity)), '--', 'y'])}\n"
    source = "".join(f"{head}\t{'drop ' * arity}{k}\n" for k in range(times))
    statements = desugar(parse(source + "f/history\n"))
    defines = [s for s in statements if isinstance(s, Define)]
    assert [d.word for d in defines] == ["f"] * times
    assert not any(isinstance(node, Match) for d in defines for node in d.code)
    drops = (Call("drop", HERE),) * arity
    shadowed = Listed(tuple(Quotation((*drops, Push(k))) for k in range(times - 1)))
    assert evaluate(statements)[-1] == (shadowed,)


SLOTS = st.lists(
    st.tuples(st.sampled_from(["x", "a", "_"]), st.sampled_from([None, "Int", "Text"])),
    min_size=1,
    max_size=3,
).filter(lambda slots: any(part for _, part in slots))


@given(SLOTS)
def test_a_dispatcher_row_binds_fresh_names_guards_and_repushes(
    slots: list[tuple[str, str | None]],
) -> None:
    """[law: fresh-rows] a dispatcher row binds a prime-fresh name at each input, the slot's name,
    U+2032 and its position (so `_` and a prime for `_`), never `$i`, guards each position
    typed by a type word with that word, re-pushes every input in order and calls the clause
    word."""
    written = [name if part is None else f"{name}: {part}" for name, part in slots]
    n = len(slots)
    clause, dispatcher = desugar(parse(f"f : {' '.join(written)} -- y\n\t{'drop ' * n}1\n"))
    assert isinstance(clause, Define)
    fresh = [f"{name}\u2032{j}" for j, (name, _) in enumerate(slots, 1)]
    patterns = tuple(
        Var(v) if part is None else Guarded(Var(v), part, HERE)
        for v, (_, part) in zip(fresh, slots, strict=True)
    )
    body = (*(Call(v, HERE) for v in fresh), Call(f"f/{n}/1", HERE))
    code = (Match((Row(patterns, body),), HERE),)
    effect = replace(clause.effect, fails=True)
    assert clause.clause == (n, 1)
    assert dispatcher == Define("f", effect, code, clause=(n,), clauses=(f"f/{n}/1",))


VALUES = [*ATOMS, ("#a", "Symbol")]


@given(st.sampled_from(VALUES), st.sampled_from(TYPES), st.integers(0, 2))
def test_a_call_no_row_fits_fails_at_the_dispatcher(
    value: tuple[str, str], word: str, above: int
) -> None:
    """[law: no-clause-fails] a call no row fits is `no row matches` +fail at the dispatcher's
    span, its first clause's head; a lone typed clause's one-row dispatcher keeps the type and
    the +fail."""
    padding = "".join(f"k{i} : -- y\n\t1\n" for i in range(above))
    source = f"{padding}f : x: {word} -- y\n\tdrop #ok\n"
    written, kind = value
    assert top(source + "f/effect\n") == Listed(("x:", word, "--", "y", "+fail"))
    if kind == word:
        assert run(source + f"{written} f\n") == "#ok\n"
        return
    with pytest.raises(FplError, match=rf"^ERROR: {2 * above + 1}:1 no row matches$"):
        run(source + f"{written} f\n")


@given(GROUPS, st.sampled_from([None, "Int", "Text"]))
def test_resugar_writes_clauses_as_written_and_no_dispatcher(
    groups: set[int], part: str | None
) -> None:
    """[law: dispatched-resugar] resugar writes a dispatched word's clauses back as written,
    `x: T` included, and never writes back a dispatcher `f/n`."""
    source = clauses(groups, part)
    statements = desugar(parse(source))
    assert resugar(statements) == parse(source)


def test_a_redefined_typed_clause_keeps_its_path_and_its_history() -> None:
    """[law: clause-path] a same-key redefinition of a dispatched word's clause shadows it at
    `f/1/1`, whose history `f/1/history` answers, under the one dispatcher `f/1`."""
    source = LONE + "f : x: Int -- y\n\tdrop #new\n"
    defines = [s for s in desugar(parse(source)) if isinstance(s, Define)]
    assert [d.word for d in defines] == ["f/1/1", "f/1", "f/1/1"]
    assert run(source + "5 f\nf/1/history\n") == "#new\n⟨ [ drop #int ] ⟩\n"
