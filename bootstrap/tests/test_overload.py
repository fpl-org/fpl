"""Typed dispatch (design 09): the type words, the types of an effect's slots and the words of
a definition's clauses."""

from collections.abc import Iterator
from dataclasses import fields, replace
from itertools import combinations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fpl.ast_core import (
    Bind,
    Call,
    Define,
    Effect,
    Equal,
    Guarded,
    Inverse,
    Listed,
    Match,
    Node,
    Pattern,
    Push,
    Quotation,
    Refuse,
    Row,
    Run,
    Statement,
    Strand,
    Value,
    Var,
    Wild,
)
from fpl.desugar import desugar, resugar
from fpl.driver import checked, run
from fpl.errors import FailError, FplError, Span
from fpl.eval import BUILTINS, effect_line, evaluate
from fpl.parse import parse
from fpl.types import (
    Arrow,
    Dispatch,
    Kind,
    Typing,
    Verdict,
    chosen,
    elaborate,
    reported,
    sort,
    verdict,
)

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


def test_a_lone_typed_clause_is_guarded() -> None:
    """[law: no-clause-fails] a lone `f : x: Int -- y` fails on `“a” f` with `no row matches`
    at its head, and runs its body on 5."""
    assert run(LONE + "5 f\n") == "#int\n"
    with pytest.raises(FplError, match=r"^ERROR: 1:1 no row matches$"):
        run(LONE + "“a” f\n")


PARTIAL = "p : x -- b\n\tmatch\n\t\t0\t1\n"


@given(st.sampled_from([("5", "#any"), ("0", "#p")]))
def test_a_guard_that_misses_is_not_fitting(call: tuple[str, str]) -> None:
    """[law: guard-failure] a guard whose test word fails with `no row matches` counts as a
    miss, in a dispatcher row and in a match row alike: with `p : x -- b` a match whose one row
    is `0 1`, `f : x: p -- y` beside `f : x -- y`/`drop #any` prints `#any` for `5 f`."""
    value, printed = call
    row = "f : x -- y\n\tmatch\n\t\t( _ ∈ p )\t#p\n\t\t_\t#any\n"
    clauses = "f : x: p -- y\n\tdrop #p\nf : x -- y\n\tdrop #any\n"
    assert run(PARTIAL + row + f"{value} f\n") == f"{printed}\n"
    assert run(PARTIAL + clauses + f"{value} f\n") == f"{printed}\n"


TWO = "two : x -- b\n\t2 -\n\tmatch\n\t\t0\t1\n\t\t_\t0\n"


def test_an_error_in_a_guard_propagates() -> None:
    """[law: guard-failure] a predicate used as a slot type must be total over the values it can
    meet: an error other than the miss propagates out of the call as that error, so with `two`,
    `f : x: Text`/`drop #text` then `f : x: two`/`drop #two`, `“a” f` gives `arithmetic on a
    non-number` from `two`, not `#text`."""
    clauses = "f : x: Text -- y\n\tdrop #text\nf : x: two -- y\n\tdrop #two\n"
    assert run(TWO + clauses + "2 f\n") == "#two\n"
    with pytest.raises(FplError, match=r"^ERROR: 2:4 arithmetic on a non-number$"):
        run(TWO + clauses + "“a” f\n")


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


POS = "pos : x -- b\n\tmatch\n\t\t1\t1\n\t\t_\t0\n"


@given(st.sampled_from(["1", "2", "“a”", "#s"]), st.sampled_from(["r: pos", "( r: pos )"]))
def test_a_typed_pattern_matches_as_its_ascription(value: str, written: str) -> None:
    """[law: typed-pattern] `r: pos` in a match row or a head group is
    `Guarded(Var("r"), "pos")` and matches exactly as `r ∈ pos` does."""
    rows = "f : x -- y\n\tmatch\n\t\t{}\tr\n\t\t_\t#no\n"
    typed = POS + rows.format(written) + f"{value} f\n"
    ascribed = POS + rows.format("( r ∈ pos )") + f"{value} f\n"
    assert run(typed) == run(ascribed)
    define = [s for s in desugar(parse(typed)) if isinstance(s, Define)][-1]
    match define.code:
        case (Match(rows=(Row(patterns=(pattern,)), _)),):
            assert pattern == Guarded(Var("r"), "pos", Span(1, 1))
        case _:
            pytest.fail(f"not a two-row match: {define.code}")


@given(st.booleans())
def test_an_empty_group_is_refused(head: bool) -> None:
    """[law: empty-group] `( )` as a pattern is refused with an error, never a crash in
    `inverse`, in a match row and in a head."""
    source = "f : ( ) -- y\n\t1\n" if head else "f : x -- y\n\tmatch\n\t\t( )\t1\n"
    with pytest.raises(FplError, match=r"^ERROR: 1:1 no evaluator yet$"):
        run(source)


SHAPES = "circle : r -- shape\n\t#circle swap pair\nrect : w h -- shape\n\t#rect swap pair pair\n"
AREA = "area : ( circle r ) -- n\n\tr dup times\n"


@given(st.integers(0, 9))
def test_a_head_group_binds_its_names_in_the_clause(radius: int) -> None:
    """[law: head-group] a clause with a group slot `( p )` has as code its own one-row match,
    so `p`'s names are bound in the body; its dispatcher tests the group with the generated word
    `f/n/i`, a prime and `k`, 1 where `( p )` matches, else 0, without consuming the value."""
    assert run(SHAPES + AREA + f"{radius} circle area\n") == f"{radius * radius}\n"
    defines = desugar(parse(SHAPES + AREA))
    for shape, fits in ((f"{radius} circle", 1), (f"{radius} | 1 rect", 0)):
        value = top(SHAPES + shape + "\n")
        tested = Run((Push(value), Call("area/1/1\N{PRIME}1", Span(1, 1))))
        assert evaluate((*defines, tested))[-1] == (fits,)
    with pytest.raises(FplError, match=r"^ERROR: 5:1 no row matches$"):
        run(SHAPES + AREA + f"{radius} area\n")


def test_p7_with_the_circle_clause_alone() -> None:
    """[law: head-group] P7 with the circle clause alone: `3 circle area` prints 9, `5 area`
    fails at the dispatcher, the area head; the clause and its test word are not written back."""
    assert run(SHAPES + AREA + "3 circle area\n") == "9\n"
    statements = desugar(parse(SHAPES + AREA))
    words = [s.word for s in statements if isinstance(s, Define)]
    assert words[2:] == ["area/1/1", "area/1/1\N{PRIME}1", "area/1"]
    assert resugar(statements) == parse(SHAPES)


def test_a_pin_in_a_head_group_is_refused() -> None:
    """[S37] `$y` inside a head group is refused: the other inputs are bound by fresh names, so
    the pin could not resolve (hole head-group-pin)."""
    with pytest.raises(FplError, match=r"^ERROR: 1:1 no evaluator yet$"):
        run(SHAPES + "area : y  ( circle $y ) -- n\n\tdrop 1\n")


def test_a_head_group_looks_its_constructor_up_from_its_own_definition() -> None:
    """[law: head-group] the constructor in a head group is found from the definition it
    heads, not the one desugared before it: b/area's ( circle r ) is b/circle, though
    b/c/circle comes between them."""
    nested = (
        "b/\n\tcircle : r -- shape\n\t\t#circle swap pair\n"
        "\tc/\n\t\tcircle : r -- shape\n\t\t\t#other swap pair\n"
        "\tarea : ( circle r ) -- n\n\t\tr dup times\n"
    )
    assert run(nested + "3 b/circle b/area\n") == "9\n"
    with pytest.raises(FplError, match=r"^ERROR: 7:2 no row matches$"):
        run(nested + "3 b/c/circle b/area\n")


def test_a_thunk_slot_is_not_a_head_group() -> None:
    """[law: head-group] the [ ] of a thunk slot is the slot's type, not a group: with t: [ ]
    before ( circle r ), the group is ( circle r ), which binds r and matches a circle."""
    thunked = "f : t: [ ]  ( circle r ) -- y\n\tdrop r\n"
    assert run(SHAPES + thunked + "[ ] 3 circle f\n") == "3\n"
    with pytest.raises(FplError, match=r"^ERROR: 5:1 no row matches$"):
        run(SHAPES + thunked + "[ ] [ ] f\n")


F = "f : x: Int -- y\n\t1 +\nf : x: Text -- y\n\tdrop #text\n"
G = "g : x -- y\n\tf\n"


def test_two_typed_clauses_of_one_arity_are_dispatched() -> None:
    """[law: dispatcher-effect] F's Int and Text clauses answer through f and g; `#s` fits no
    row and fails at F's first head; a catch-all added later takes `#s` and removes the +fail,
    while `5 f` still takes the Int clause."""
    assert run(F + G + "5 f\n“a” f\n5 g\n“a” g\n") == "6\n#text\n6\n#text\n"
    for call in ("#s g", "#s f"):
        with pytest.raises(FplError, match=r"^ERROR: 1:1 no row matches$"):
            run(F + G + call + "\n")
    assert top(F + "f/1/1/effect\n") == Listed(("x:", "Int", "--", "y"))
    assert top(F + "f/1/2/effect\n") == Listed(("x:", "Text", "--", "y"))
    other = F + G + "f : x -- y\n\tdrop #other\n"
    assert run(other + "#s g\n5 f\n") == "#other\n6\n"
    assert top(other + "f/effect\n") == Listed(("x", "--", "y"))


@given(
    st.lists(st.sampled_from(TYPES), min_size=1, max_size=4, unique=True),
    st.integers(0, 4),
    st.booleans(),
)
def test_a_dispatcher_effect_keeps_what_its_clauses_share(
    types: list[str], at: int, catchall: bool
) -> None:
    """[law: dispatcher-effect] a dispatcher's effect takes its slot names and kinds from its
    group's first clause in written order, keeps a type at a position only where all its
    clauses have that same type, and carries +fail iff its group has no all-untyped clause."""
    parts: list[str | None] = list(types)
    if catchall:
        parts.insert(min(at, len(parts)), None)
    heads = [f"v{i}" if part is None else f"v{i}: {part}" for i, part in enumerate(parts)]
    source = "".join(f"f : {head} -- y\n\tdrop {i}\n" for i, head in enumerate(heads))
    first = ("v0",) if len(parts) > 1 or parts[0] is None else ("v0:", parts[0])
    fails = () if catchall else ("+fail",)
    assert top(source + "f/effect\n") == Listed((*first, "--", "y", *fails))
    assert top(source + "f/1/effect\n") == top(source + "f/effect\n")


KINDS = {"value": "x{}", "thunk": "t{}: [ ]", "code": "c{}: Code"}
kinds = st.lists(st.sampled_from(list(KINDS)), min_size=1, max_size=2)


@given(kinds, kinds)
def test_clauses_of_one_arity_agree_on_slot_kinds(first: list[str], second: list[str]) -> None:
    """[law: slot-agreement] clauses of one arity agree on the slot kind at every position, else
    the later head is refused (`f/1/2 takes a thunk at 1, f/1/1 a value`); clauses that agree
    are accepted."""
    second = (second * 2)[: len(first)]
    n = len(first)
    written = [KINDS[k].format(i) for i, k in enumerate(first)]
    typed = [f"x{i}: Int" if k == "value" else KINDS[k].format(i) for i, k in enumerate(second)]
    body = "\t" + "drop " * n + "1\n"
    source = f"f : {' '.join(written)} -- y\n{body}f : {' '.join(typed)} -- y\n{body}"
    differ = [(j, a, b) for j, (a, b) in enumerate(zip(first, second, strict=True), 1) if a != b]
    if not differ:
        assert run(source) == ""
        return
    j, earlier, later = differ[0]
    refusal = rf"^ERROR: 3:1 f/{n}/2 takes a {later} at {j}, f/{n}/1 a {earlier}$"
    with pytest.raises(FplError, match=refusal):
        run(source)


@given(st.integers(1, 3), st.integers(1, 3))
def test_clauses_of_one_arity_leave_as_many_values(first: int, second: int) -> None:
    """[law: output-count] clauses of one arity leave as many values, else the later head is
    refused; clauses that agree are accepted."""

    def clause(head: str, outs: int) -> str:
        names = " ".join(f"y{i}" for i in range(outs))
        return f"f : {head} -- {names}\n\tdrop 1{' dup' * (outs - 1)}\n"

    source = clause("x", first) + clause("x: Int", second) + "5 f\n"
    if first == second:
        assert run(source) == run("1" + " dup" * (first - 1) + "\n")
        return
    with pytest.raises(FplError, match=rf"^ERROR: 3:1 f/1/2 leaves {second}, f/1/1 {first}$"):
        run(source)


PQ = "p : x -- b\n\tdrop 1\nq : x -- b\n\tdrop 1\n"


@given(st.lists(st.sampled_from([None, "Int", "p", "q"]), min_size=1, max_size=6))
def test_a_clause_keeps_the_ordinal_of_its_key(keys: list[str | None]) -> None:
    """[law: clause-key] a clause's key is its per-input parts; a later clause with an existing
    key shadows that clause and keeps its path ordinal, which is also its age among equally
    specific clauses; a clause with a new key takes the next ordinal, and no path moves."""
    if set(keys) == {None}:
        return
    order = list(dict.fromkeys(keys))
    heads = ["x" if key is None else f"x: {key}" for key in keys]
    source = PQ + "".join(f"f : {h} -- y\n\tdrop {k}\n" for k, h in enumerate(heads))
    statements = desugar(parse(source))
    clauses = [s.word for s in statements if isinstance(s, Define) and len(s.clause) == 2]
    assert clauses == [f"f/1/{order.index(key) + 1}" for key in keys]
    typed = [key for key in order if key is not None]
    winner = typed[-1] if typed else None
    assert run(source + "1 f\n") == f"{max(k for k, key in enumerate(keys) if key == winner)}\n"
    for i, key in enumerate(order, 1):
        shadowed = [k for k, other in enumerate(keys) if other == key][:-1]
        bodies = "".join(f" [ drop {k} ]" for k in shadowed)
        assert run(source + f"f/1/{i}/history\n") == f"⟨{bodies} ⟩\n".replace("⟨ ⟩", "⟨⟩")


def test_a_shadowing_clause_keeps_its_age() -> None:
    """[law: clause-key] `f : x: p`, `f : x: q`, then `f : x: p` again: a call both accept goes
    to the q clause, the newest by path ordinal, and `f/1/1/history` holds the first p body."""
    source = PQ + "f : x: p -- y\n\tdrop #p1\nf : x: q -- y\n\tdrop #q\nf : x: p -- y\n\tdrop #p2\n"
    assert run(source + "1 f\nf/1/1/history\n") == "#q\n⟨ [ drop #p1 ] ⟩\n"


ONE = "one : x -- b\n\tmatch\n\t\t1\t1\n\t\t_\t0\n"
ONE_CLAUSE = "f : x: one -- y\n\tdrop #one\n"
INT_CLAUSE = "f : x: Int -- y\n\tdrop #int\n"


@given(st.booleans(), st.sampled_from(["1", "2", "“a”"]))
def test_the_most_specific_then_the_newest_fitting_clause_wins(one_first: bool, value: str) -> None:
    """[law: specificity] among the clauses that fit a call the most specific wins and, among
    equally specific ones, the newest by path ordinal: `f : x: one` then `f : x: Int` sends
    `1 f` to the Int clause, written the other way round to the one clause (P6)."""
    clauses = ONE_CLAUSE + INT_CLAUSE if one_first else INT_CLAUSE + ONE_CLAUSE
    fits = {"one": value == "1", "int": value != "“a”"}
    written = ["one", "int"] if one_first else ["int", "one"]
    winner = next((word for word in reversed(written) if fits[word]), None)
    if winner is None:
        with pytest.raises(FplError, match=r"^ERROR: 5:1 no row matches$"):
            run(ONE + clauses + f"{value} f\n")
        return
    assert run(ONE + clauses + f"{value} f\n") == f"#{winner}\n"


def test_p1_and_p2() -> None:
    """[law: specificity] P1 prints `#int` then `#any`; P2, Draft 4's collide, prints `#boom
    #boom #bounce #miss`."""
    p1 = "f : x -- y\n\tdrop #any\nf : x: Int -- y\n\tdrop #int\n5 f\n“a” f\n"
    assert run(p1) == "#int\n#any\n"
    p2 = (
        "ship : x -- b\n\tmatch\n\t\t#ship\t1\n\t\t_\t0\n"
        "rock : x -- b\n\tmatch\n\t\t#rock\t1\n\t\t_\t0\n"
        "collide : a: rock  b: ship -- o\n\tdrop drop #boom\n"
        "collide : a: ship  b: rock -- o\n\tswap collide\n"
        "collide : a: ship  b: ship -- o\n\tdrop drop #bounce\n"
        "collide : a  b -- o\n\tdrop drop #miss\n"
        "#rock | #ship collide\n#ship | #rock collide\n"
        "#ship | #ship collide\n#rock | #rock collide\n"
    )
    assert run(p2) == "#boom\n#boom\n#bounce\n#miss\n"


def rowed(define: Define) -> list[str]:
    """The clause each row of a dispatcher calls, in row order."""
    match define.code:
        case (Match(rows=rows),):
            return [call.name for row in rows for call in row.body[-1:] if isinstance(call, Call)]
        case _:
            return []


@given(
    st.lists(
        st.tuples(st.sampled_from([None, "p", "q"]), st.sampled_from([None, "p", "q"])),
        min_size=1,
        max_size=5,
    )
)
def test_rows_sort_by_typed_count_then_newest(keys: list[tuple[str | None, str | None]]) -> None:
    """[law: dispatch-order] a dispatcher's real rows sort by typed-position count descending
    and, at equal count, newest first by path ordinal; a crossing pair whose meet is not a
    clause is refused."""
    order = list(dict.fromkeys(keys))
    typings = [frozenset(j for j, part in enumerate(key) if part) for key in order]
    slots = [[f"{v}: {t}" if t else v for v, t in zip("ab", key, strict=True)] for key in keys]
    heads = [" ".join(slot) for slot in slots]
    source = PQ + "".join(f"f : {h} -- y\n\tdrop drop {k}\n" for k, h in enumerate(heads))
    typed = list(zip(order, typings, strict=True))
    crossing = [(a, b) for a, s in typed for b, t in typed if s - t]
    meets = {tuple(x or y for x, y in zip(a, b, strict=True)) for a, b in crossing}
    if not meets <= set(order):
        with pytest.raises(FplError, match=r" is ambiguous with f/2/\d at "):
            desugar(parse(source))
        return
    if len(order) == 1 and not typings[0]:
        return
    dispatcher = next(s for s in desugar(parse(source)) if isinstance(s, Define) and s.clauses)
    ranked = sorted(range(len(order)), key=lambda i: (-len(typings[i]), -i))
    assert rowed(dispatcher) == [f"f/2/{i + 1}" for i in ranked]


TEXT = "Text : x -- b\n\tdrop 1\n"


@given(st.booleans(), st.sampled_from(["5", "“a”"]))
def test_a_redefined_type_word_is_disjoint_from_nothing(redefined: bool, value: str) -> None:
    """[law: shadowed-disjoint] two different unshadowed builtin type words at one position make
    two clauses disjoint and nothing else does; a type word the program redefines is a user
    predicate everywhere, run as the slot's guard and disjoint from nothing."""
    prelude = TEXT if redefined else ""
    source = prelude + "f : x: Int -- y\n\tdrop #int\nf : x: Text -- y\n\tdrop #text\n"
    int_wins = value == "5" and not redefined
    assert run(source + f"{value} f\n") == ("#int\n" if int_wins else "#text\n")
    body = "\tdrop drop drop 1\n"
    h = f"h : x: Int  y: Int  z -- o\n{body}h : x: Text  y  z: Int -- o\n{body}"
    assert run(prelude + h) == ""
    if redefined:
        refusal = r"^ERROR: 3:1 ambiguous call to h: h/3/1 and h/3/2 both fit$"
        with pytest.raises(FplError, match=refusal):
            run(prelude + h + "1 | 2 | 3 h\n")


P7 = SHAPES + AREA + "area : ( rect w h ) -- n\n\tw h times\narea : s -- n\n\tdrop 0\n"


@given(st.integers(0, 9), st.integers(0, 9), st.integers(0, 9))
def test_head_groups_dispatch_beside_other_clauses(radius: int, w: int, h: int) -> None:
    """[law: head-group] beside other clauses a group clause's dispatcher row binds a prime-fresh
    `_` at the group and tests it with the generated word `f/n/i`, a prime and `k`, without
    consuming the value: P7 prints the circle's and the rect's areas, and 0."""
    runs = f"{radius} circle area\n{w} | {h} rect area\n5 area\n"
    assert run(P7 + runs) == f"{radius * radius}\n{w * h}\n0\n"
    dispatcher = next(s for s in desugar(parse(P7)) if isinstance(s, Define) and s.clauses)
    blank = Var("_\N{PRIME}1")
    tests = [Guarded(blank, f"area/1/{i}\N{PRIME}1", Span(5, 1)) for i in (2, 1)]
    match dispatcher.code:
        case (Match(rows=rows),):
            patterns = [row.patterns for row in rows]
            assert patterns == [(tests[0],), (tests[1],), (Var("s\N{PRIME}1"),)]
        case _:
            pytest.fail(f"not a match: {dispatcher.code}")


P3 = "g : x: Int  y -- z\n\tdrop drop #left\ng : x  y: Int -- z\n\tdrop drop #right\n"
MEET = "g : x: Int  y: Int -- z\n\tdrop drop #both\n"


@given(st.integers(0, 2))
def test_p3_is_refused_until_its_meet_is_a_clause(at: int) -> None:
    """[law: static-ambiguity] P3 is refused at 3:1, `g/2/2 is ambiguous with g/2/1 at x: Int
    y: Int`; with the meet written anywhere it prints `#both #left #right`."""
    runs = "1 | 2 g\n1 | “a” g\n“a” | 2 g\n"
    refusal = r"^ERROR: 3:1 g/2/2 is ambiguous with g/2/1 at x: Int  y: Int$"
    with pytest.raises(FplError, match=refusal):
        run(P3 + runs)
    lines = P3.splitlines(keepends=True)
    clauses = ["".join(lines[:2]), "".join(lines[2:])]
    clauses.insert(at, MEET)
    assert run("".join(clauses) + runs) == "#both\n#left\n#right\n"


PARTS3 = st.tuples(*[st.sampled_from([None, "Int", "Text", "p"])] * 3)


@given(PARTS3, PARTS3, st.booleans())
def test_crossing_clauses_are_refused_unless_their_meet_is_a_clause(
    a: tuple[str | None, ...], b: tuple[str | None, ...], meet: bool
) -> None:
    """[law: static-ambiguity] two clauses of one arity whose typed positions cross, that are
    not disjoint and agree wherever both are typed, are refused at the later head before
    anything runs, unless the meet is itself a clause; a pair typed two ways at one input is
    accepted, a call both fit refused at run time."""
    s, t = ({j for j, part in enumerate(key) if part} for key in (a, b))
    pairs = list(zip(a, b, strict=True))
    clash = [{x, y} for x, y in pairs if x and y and x != y]
    if s <= t or t <= s or {"Int", "Text"} in clash:
        return
    joined = tuple(x or y for x, y in pairs)
    slots = [[f"{v}: {p}" if p else v for v, p in zip("xyz", key, strict=True)] for key in (a, b)]
    keys = [*slots, [f"{v}: {p}" if p else v for v, p in zip("xyz", joined, strict=True)]]
    heads = [" ".join(key) for key in keys[: 2 + meet]]
    clauses = "".join(f"h : {h} -- o\n\tdrop drop drop 1\n" for h in heads)
    source = "p : x -- b\n\tdrop 1\n" + clauses
    if clash or meet:
        assert run(source) == ""
    else:
        refusal = f"^ERROR: 5:1 h/3/2 is ambiguous with h/3/1 at {'  '.join(keys[2])}$"
        with pytest.raises(FplError, match=refusal):
            desugar(parse(source))


H = (
    "h : a: one  b: Int  c -- o\n\tdrop drop drop #first\n"
    "h : a: Int  b  c: Int -- o\n\tdrop drop drop #second\n"
)
COVER = "h : a: one  b: Int  c: Int -- o\n\tdrop drop drop #both\n"
AMBIGUOUS = r"^ERROR: 5:1 ambiguous call to h: h/3/1 and h/3/2 both fit$"


@given(st.booleans())
def test_p5_refuses_a_call_both_crossing_clauses_fit(covered: bool) -> None:
    """[law: runtime-ambiguity] for a crossing pair whose meet is undefined the dispatcher has a
    synthetic row that conjoins both clauses' tests as nested `Guarded`, sorts after the real
    rows of equal count and refuses at the dispatcher's span: P5 prints `#first`, `#second` and
    refuses `1 | 2 | 3 h`, and with its cover clause added prints `#both` there."""
    source = ONE + H + (COVER if covered else "")
    assert run(source + "1 | 2 | #c h\n2 | 2 | 3 h\n") == "#first\n#second\n"
    if covered:
        assert run(source + "1 | 2 | 3 h\n") == "#both\n"
    else:
        with pytest.raises(FplError, match=AMBIGUOUS):
            run(source + "1 | 2 | 3 h\n")
    span = Span(5, 1)
    ints = Guarded(Wild(), "Int", span)
    both = (Guarded(Guarded(Wild(), "one", span), "Int", span), ints, ints)
    dispatcher = next(s for s in desugar(parse(source)) if isinstance(s, Define) and s.clauses)
    match dispatcher.code:
        case (Match(rows=rows),):
            refusing = [i for i, row in enumerate(rows) if isinstance(row.body[0], Refuse)]
            assert refusing == [int(covered)]
            assert rows[int(covered)].patterns == both
        case _:
            pytest.fail(f"not a match: {dispatcher.code}")


@given(st.booleans())
def test_an_ambiguity_is_a_refusal_not_a_miss(catch_all: bool) -> None:
    """[law: refusal-not-fail] an ambiguity refusal is an error, not +fail: `fallible` never
    counts a refusing row and it adds no +fail to any effect line, so P5's `h/effect` is +fail
    only for want of a clause taking every value."""
    tail = "h : a  b  c -- o\n\tdrop drop drop #any\n" if catch_all else ""
    fails = "" if catch_all else " “+fail”"
    assert run(ONE + H + tail + "h/effect\n") == f"⟨ “a” “b” “c” “--” “o”{fails} ⟩\n"
    with pytest.raises(FplError, match=AMBIGUOUS) as caught:
        run(ONE + H + tail + "1 | 2 | 3 h\n")
    assert not isinstance(caught.value, FailError)


type Key = tuple[str | None, ...]
CIRCLE = "( circle r )"
FITS = {"Int": "1", "Text": "“a”", "one": "1", CIRCLE: "3 circle"}
CHOICES = st.integers(1, 2).flatmap(
    lambda n: st.tuples(
        st.lists(st.tuples(*[st.sampled_from([None, *FITS])] * n), min_size=1, max_size=3),
        st.tuples(*[st.sampled_from(["1", "“a”", "#s", "3 circle"])] * n),
    )
)
ANSWERS = {
    "refused": r" is ambiguous with f/",
    "none": r"^ERROR: 9:1 no row matches$",
    "ambiguous": r"^ERROR: 9:1 ambiguous call to f: f/\d/\d and f/\d/\d both fit$",
}


def positions(key: Key) -> frozenset[int]:
    """A generated clause's typed inputs."""
    return frozenset(j for j, part in enumerate(key) if part)


def slotted(position: int, part: str | None) -> str:
    """A generated slot: its name, typed by part; a group names its radius by position."""
    name = "ab"[position]
    if part == CIRCLE:
        return f"( circle r{position} )"
    return name if part is None else f"{name}: {part}"


def refused(keys: list[Key]) -> bool:
    """The static check: two keys crossing, not disjoint, whose meet is defined and not a key."""
    for a, b in combinations(keys, 2):
        pairs = list(zip(a, b, strict=True))
        crossing = not (positions(a) <= positions(b) or positions(b) <= positions(a))
        disjoint = any(x != y and {x, y} <= {"Int", "Text"} for x, y in pairs)
        clash = any(x and y and x != y for x, y in pairs)
        if crossing and not disjoint and not clash and tuple(x or y for x, y in pairs) not in keys:
            return True
    return False


def answered(keys: list[Key], values: tuple[str, ...]) -> str:
    """B by brute force over the written keys: the newest body of the newest of the most specific
    fitting clauses when they share their typed inputs, else `ambiguous`, `none` or `refused`."""
    order = list(dict.fromkeys(keys))
    if refused(order):
        return "refused"
    fitting = [
        key
        for key in order
        if all(part is None or FITS[part] == value for part, value in zip(key, values, strict=True))
    ]
    best = [key for key in fitting if not any(positions(key) < positions(o) for o in fitting)]
    if not best:
        return "none"
    if len({positions(key) for key in best}) > 1:
        return "ambiguous"
    newest = max(best, key=order.index)
    return f"#k{max(i for i, key in enumerate(keys) if key == newest)}"


@given(CHOICES)
def test_a_dispatcher_answers_as_b_does(choice: tuple[list[Key], tuple[str, ...]]) -> None:
    """[law: clause-choice] over generated clause sets of arity 1-2 with slots from untyped,
    `Int`, `Text`, the predicate `one` and the group `( circle r )`, every accepted set's
    dispatcher answers a call with the newest of its most specific fitting clauses when they
    share one set of typed positions, refuses it as ambiguous when they do not, and fails with
    `no row matches` when none fits, as a brute-force oracle over the specificity order
    computes."""
    keys, values = choice
    clauses = ""
    for i, key in enumerate(keys):
        head = "  ".join(slotted(j, part) for j, part in enumerate(key))
        body = ["drop"] * sum(part != CIRCLE for part in key) + [f"#k{i}"]
        clauses += f"f : {head} -- y\n\t{' '.join(body)}\n"
    source = SHAPES + ONE + clauses + " | ".join(values) + " f\n"
    expected = answered(keys, values)
    if expected in ANSWERS:
        with pytest.raises(FplError, match=ANSWERS[expected]):
            run(source)
        return
    assert run(source) == f"{expected}\n"


FG = "f : x: Int -- y\n\t1 +\nf : x: Text -- y\n\tdrop #text\ng : x -- y\n\tf\n"
TEXT_FIRST = "f : x: Text -- y\n\tdrop #t\nf : x -- y\n\tdrop 1\n"


def goal(source: str) -> str:
    """The arrow of the one goal a program meets, as its effect line."""
    (met,) = checked(source)[1]
    return reported(met).split(" ? : ")[1]


LONE_INT = "f : x: Int -- y\n\t1 +\n"
WITNESS = (
    "p : x -- b\n\tdrop 1\nq : x -- b\n\tdrop 1\n"
    "f : x: p  y  z: p -- o\n\tdrop drop drop 1\n"
    "f : x: q  y: q  z -- o\n\tdrop drop drop “b”\n"
    "f : x  y: Symbol  z: Symbol -- o\n\tdrop drop drop #c\n"
)
ONE_SYMBOL = ONE + "f : x: one -- y\n\t1 +\nf : x: Symbol -- y\n\tdrop #s\n"
RESOLVED = [
    (FG, "“a” f ?", "symbol --"),
    (FG, "5 f ?", "number --"),
    (FG, "5 g ?", "value --"),
    (TEXT_FIRST, "“a” f ?", "value --"),
    (TEXT_FIRST, "5 f ?", "number --"),
    (WITNESS, "1 | #s | #s f ?", "value --"),
    (LONE_INT + G, "5 g ?", "number --"),
    (ONE_SYMBOL, "1 f ?", "number --"),
    (ONE_SYMBOL, "“a” f ?", "value --"),
]


@given(st.sampled_from(RESOLVED))
def test_types_resolves_a_dispatch_where_one_clause_row_survives(
    case: tuple[str, str, str],
) -> None:
    """[law: static-verdict] types prunes the rows in order, dropping sure misses and stopping
    after the first sure fit, and resolves a call to a clause's arrow only when exactly one
    row survives, it is real and no argument is an `Input`; a surviving synthetic row, an
    `Input` argument and a maybe row whose clause refuses the sorts keep the dispatcher's. A
    guarded row is never a sure fit, so TEXT_FIRST's `“a” f` keeps its catch-all row too."""
    clauses, line, arrow = case
    assert goal(clauses + line + "\n") == arrow


@given(
    st.sampled_from([(LONE_INT + G, "“a” g"), (FG, "#s f"), (FG, "#s g"), (ONE_SYMBOL, "“a” f")])
)
def test_a_call_types_leaves_unresolved_fails_at_run_time(case: tuple[str, str]) -> None:
    """[law: static-verdict] a sure miss, an `Input` argument and a maybe row whose clause
    refuses the sorts are never refused statically: the call is `no row matches` at run time."""
    clauses, line = case
    with pytest.raises(FailError, match=r"^ERROR: \d+:1 no row matches$"):
        run(clauses + line + "\n")


def test_the_witness_refuses_at_run_time() -> None:
    """[law: static-verdict] the §3.6 witness's synthetic rows survive before its sure fit, so
    the call is left to the dispatcher, which refuses it."""
    with pytest.raises(FplError, match=r"ambiguous call to f: f/3/1 and f/3/2 both fit$"):
        run(WITNESS + "1 | #s | #s f\n")


@given(st.booleans())
def test_a_redefined_type_word_gets_no_static_verdict(redefined: bool) -> None:
    """[law: shadowed-verdict] a type word the program redefines gets no static verdict: its
    rows are maybe, so `5 f` over an `Int` and a `Text` clause stays with the dispatcher."""
    text = "Text : x -- b\n\tdrop 1\n" if redefined else ""
    source = text + "f : x: Int -- y\n\tdrop #i\nf : x: Text -- y\n\tdrop “t”\n5 f ?\n"
    assert goal(source) == ("value --" if redefined else "symbol --")


CELLS = (Var("x"), Wild(), Equal(Push(1)), Inverse("pair", (Var("a"), Var("b")), Span(1, 1)))


@given(st.sampled_from(CELLS), st.sampled_from([*TYPES, "one"]), st.sampled_from(list(Kind)))
def test_a_guarded_row_is_never_a_sure_fit(inner: Pattern, test: str, have: Kind) -> None:
    """[law: static-verdict] a row whose cell is a guard or an ascription, `( p ∈ w )` or
    `x: w`, is never a sure fit, whatever its pattern, its word and the value's sort: at most
    maybe, so pruning never stops at it and the rows after it stay (TEXT_FIRST's `“a” f`)."""
    arrows = elaborate(desugar(parse(ONE)))[0]
    row = Row((Guarded(inner, test, Span(1, 1)),), ())
    assert verdict(row, (have,), arrows) is not Verdict.YES


@given(st.sampled_from(CELLS[2:]), st.sampled_from(list(Kind)))
def test_a_literal_or_a_constructor_only_may_fit(cell: Pattern, have: Kind) -> None:
    """[law: static-verdict] types compares no values, so a literal or a constructor cell
    neither surely fits nor surely misses a value of any sort."""
    assert verdict(Row((cell,), ()), (have,), {}) is Verdict.MAYBE


SORTED = {"1": Kind.NUMBER, "“a”": Kind.TEXT, "#s": Kind.SYMBOL}
LEAVES = (Kind.NUMBER, Kind.TEXT, Kind.SYMBOL)
AGREEING = st.integers(1, 2).flatmap(
    lambda n: st.tuples(
        st.lists(
            st.tuples(*[st.sampled_from([None, "Int", "Text", "one"])] * n),
            min_size=1,
            max_size=3,
            unique=True,
        ),
        st.tuples(*[st.sampled_from(list(SORTED))] * n),
    )
)


def leaving(kind: Kind, n: int) -> str:
    """A clause body over n inputs leaving one value of the kind; a number is its top input
    plus one, which constrains that input."""
    if kind is Kind.NUMBER:
        return "1 +" + " swap drop" * (n - 1)
    return " ".join(["drop"] * n + ["“b”" if kind is Kind.TEXT else "#c"])


@given(AGREEING, st.booleans())
def test_static_and_dynamic_dispatch_agree(
    choice: tuple[list[Key], tuple[str, ...]], wrapped: bool
) -> None:
    """[law: static-dynamic] whenever types resolves a call to a clause, the run takes that
    clause, or fails with `no row matches` only when that clause's row was a maybe; it never
    takes another clause and never refuses; a wrapper's call on its own input is never
    refused statically."""
    keys, values = choice
    names = "ab"[: len(values)]
    clauses = ONE
    for key, kind in zip(keys, LEAVES, strict=False):
        head = "  ".join(f"{v}: {p}" if p else v for v, p in zip(names, key, strict=True))
        clauses += f"f : {head} -- y\n\t{leaving(kind, len(values))}\n"
    wrapper = f"w : {' '.join(names)} -- y\n\tf\n"
    line = " | ".join(values) + (" w\n" if wrapped else " f\n")
    if refused(keys):
        with pytest.raises(FplError, match=" is ambiguous with "):
            desugar(parse(clauses))
        return
    statements = desugar(parse(clauses + wrapper + line))
    arrows = elaborate(statements[:-1])[0]
    dispatch = arrows.get(f"f/{len(values)}")
    if not isinstance(dispatch, Dispatch):
        return
    if wrapped:
        elaborate(statements)
        return
    sorts = tuple(SORTED[v] for v in values)
    got = chosen(Typing(sorts, {}, {}), dispatch, arrows)
    taken = [(row, row.body[-1]) for row in dispatch.rows if clause_arrow(row, arrows) is got]
    if not taken:
        return
    ((row, clause),) = taken
    assert isinstance(clause, Call)
    ordinal = int(clause.name.rsplit("/", 1)[1])
    result = outcome(statements)
    match result:
        case FailError():
            assert verdict(row, sorts, arrows) is Verdict.MAYBE
        case FplError():
            assert result.span.line == 4 + 2 * ordinal
        case _:
            assert sort(result) is LEAVES[ordinal - 1]


def clause_arrow(row: Row, arrows: dict[str, Arrow]) -> Arrow | None:
    """The arrow of the clause a dispatcher row calls; none for a refusing row."""
    match row.body[-1]:
        case Call(name=name):
            return arrows[name]
        case _:
            return None


def outcome(statements: tuple[Statement, ...]) -> Value | FplError:
    """What the one run line leaves on top, or the error it raises."""
    try:
        (stack,) = evaluate(statements, None)
    except FplError as error:
        return error
    return stack[-1]
