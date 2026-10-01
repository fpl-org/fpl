"""Pass 1 keeps what the run lines reach, resolved as the walker resolves it, and refuses what
A cannot lower by name."""

from collections.abc import Iterator
from dataclasses import fields, is_dataclass
from typing import cast

from hypothesis import given
from lower_diff import evaluated, walker_output
from lower_strategies import straight

from fpl.ast_core import (
    Call,
    Define,
    Effect,
    Equal,
    Guarded,
    Inverse,
    Match,
    Push,
    Row,
    Run,
    Statement,
    Var,
    Wild,
)
from fpl.desugar import desugar
from fpl.errors import Span
from fpl.lower.select import CoreA, RefusalKind, Refused, in_core_a, select
from fpl.parse import parse

AT = Span(1, 3)


def called(tree: object) -> Iterator[str]:
    """Every name a `Call` anywhere in `tree` spells, through every field of every node and
    value: an oracle apart from select's own walk, exact where no binder shares a word's name."""
    if isinstance(tree, Call):
        yield tree.name
    if is_dataclass(tree):
        for f in fields(tree):
            yield from called(getattr(tree, f.name))
    elif isinstance(tree, tuple):
        for item in cast(tuple[object, ...], tree):
            yield from called(item)


def reached(statements: tuple[Statement, ...]) -> dict[str, Define]:
    """The last definition of each word the run lines reach, a query reaching its word."""
    last = {s.name: s for s in statements if isinstance(s, Define)}
    todo = [n for s in statements if isinstance(s, Run) for n in called(s)]
    seen: dict[str, Define] = {}
    while todo:
        name = todo.pop().removesuffix("/doc").removesuffix("/effect")
        if name in last and name not in seen:
            seen[name] = last[name]
            todo.extend(called(last[name].code))
    return seen


@given(straight())
def test_select_keeps_output(source: str) -> None:
    """[law: select-keeps-output] For every program `straight()` draws, pass 1's output is in
    Core_A, and `fpl.eval.evaluate` on it renders as on the whole program. Core_A is judged by
    an independent oracle: exactly the reached definitions, each after the words it calls, and
    every run line in order."""
    statements = desugar(parse(source))
    selected = select(statements)
    assert isinstance(selected, CoreA)
    defines = [s for s in selected.statements if isinstance(s, Define)]
    assert {d.name: d for d in defines} == reached(statements)
    for index, define in enumerate(defines):
        earlier = {d.name for d in defines[:index]}
        assert set(reached((*defines, Run(define.code)))) - {define.name} <= earlier
    runs = [s for s in statements if isinstance(s, Run)]
    assert [s for s in selected.statements if isinstance(s, Run)] == runs
    assert in_core_a(selected.statements)
    assert evaluated(selected.statements) == walker_output(source)


def refused(statements: tuple[Define | Run, ...]) -> tuple[RefusalKind, Span, str]:
    got = select(statements)
    assert isinstance(got, Refused)
    return got.kind, got.at, got.detail


def test_a_binder_a_quotation_calls_as_a_word_is_refused() -> None:
    source = "[ dup ] →x 2 →dup x !"
    kind, at, _ = refused(desugar(parse(source)))
    assert (kind, at) == (RefusalKind.BINDER_CAPTURES, Span(1, source.index("→dup") + 1))


def test_a_binder_that_only_shadows_is_kept() -> None:
    statements = desugar(parse("5 →dup 3 dup"))
    assert select(statements) == CoreA(statements, ())


def test_code_as_data_is_level_one() -> None:
    join = Run((Push(1), Push(2), Call(",", AT)))
    assert refused((join,))[:2] == (RefusalKind.LEVEL_ONE, AT)
    word = Define("f", Effect((), ()), ())
    assert refused((word, Run((Call("f/history", AT),))))[:2] == (RefusalKind.LEVEL_ONE, AT)
    slot = Define("f", Effect(("c",), (), slots=("code",)), (Call("drop", AT),), span=AT)
    assert refused((slot, Run((Push(1), Call("f", AT)))))[:2] == (RefusalKind.LEVEL_ONE, AT)


def test_only_the_last_reached_definition_is_kept_in_component_order() -> None:
    f = Define("f", Effect((), ()), (Call("g", AT),))
    g = Define("g", Effect((), ()), (Call("f", AT), Call("h", AT)))
    h = Define("h", Effect((), ()), ())
    dead = Define("d", Effect((), ()), ())
    doc = Run((Call("f", AT), Call("h/doc", AT)))
    redefined = Define("h", Effect((), ()), (Push(1),))
    got = select((h, dead, g, f, redefined, doc))
    assert isinstance(got, CoreA)
    assert redefined in got.statements
    assert h not in got.statements
    assert got.components == (("h",), ("f", "g"))
    assert not in_core_a((dead, doc))
    assert in_core_a(got.statements)


def test_match_rows_bind_and_their_tests_are_calls() -> None:
    rows = (
        Row((Var("n"), Equal(Push(0))), (Call("n", AT),)),
        Row((Guarded(Wild(), "t", AT), Var("x")), ()),
    )
    t = Define("t", Effect(("v",), ("v",)), ())
    got = select((t, Run((Push(1), Push(2), Match(rows, AT)))))
    assert isinstance(got, CoreA)
    assert got.components == (("t",),)
    captured = Run((Push(1), Match((Row((Var("dup"),), ()),), AT), Push(2), Call("dup", AT)))
    assert refused((captured,))[:2] == (RefusalKind.BINDER_CAPTURES, AT)


def test_an_inverse_pattern_is_refused_where_it_is_written() -> None:
    source = "s : xs -- n\n\tmatch\n\t\t⟨⟩\t0\n\t\t( cons x xs )\t1\n⟨ 1 ⟩ s\n"
    assert select(desugar(parse(source))) == Refused(
        RefusalKind.INVERSE_PATTERN, Span(4, 5), "a constructor run backwards"
    )
    inverse = Row((Inverse("pair", (Var("x"), Wild()), AT),), ())
    assert refused((Run((Push(1), Match((inverse,), AT))),))[:2] == (
        RefusalKind.INVERSE_PATTERN,
        AT,
    )
