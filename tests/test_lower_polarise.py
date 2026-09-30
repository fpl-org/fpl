"""Pass 2 on straight-line code: the compiled program prints what the walker prints."""

from collections.abc import Mapping
from dataclasses import fields, is_dataclass

import icontract
import pytest
from hypothesis import given
from hypothesis import strategies as st
from lower_diff import cbpv_output, walker_output
from lower_strategies import START, broad_match, controlled, recursive, source_of, straight

from fpl.ast_core import (
    Bind,
    Call,
    Define,
    Effect,
    Equal,
    Guarded,
    Inverse,
    Keyed,
    Listed,
    Match,
    Node,
    Push,
    Quotation,
    Row,
    Run,
    Wild,
)
from fpl.cbpv.check import check
from fpl.cbpv.syntax import Comp, Effects, Fail, First, Force, Prim, Rec, Second, Thunk, Var
from fpl.desugar import desugar
from fpl.errors import FplError
from fpl.eval import effect_line, evaluate, substitute
from fpl.lower.polarise import PROBE, Lowered, polarise
from fpl.lower.select import CoreA, RefusalKind, Refused, select
from fpl.lower.walker import signature
from fpl.parse import parse


def lowered(source: str) -> CoreA:
    core = select(desugar(parse(source)))
    assert isinstance(core, CoreA)
    return core


def accepted(source: str) -> Lowered:
    """Pass 2's output for `source`, which it must lower and the checker accept."""
    result = polarise(lowered(source))
    assert not isinstance(result, Refused), result
    program, extra, _ = result
    assert check(program, signature(extra), loops=False) is None
    return result


@pytest.mark.obligation("the interpreter and the compiled program print the same")
@given(straight())
def test_lower_agrees_straight(source: str) -> None:
    """[law: lower-agrees-straight] For every program `straight()` draws, pass 2's output
    passes `check(loops=False)`, and `cbpv_output` equals `walker_output`: the same printed
    stacks, or the same error line."""
    accepted(source)
    assert cbpv_output(source) == walker_output(source)


@pytest.mark.obligation("the interpreter and the compiled program print the same")
@given(controlled())
def test_lower_agrees_controlled(source: str) -> None:
    """[law: lower-agrees-controlled] For every program `controlled()` draws (each draw holds a
    literal quotation or a control word), pass 2's output passes `check(loops=False)`, and
    `cbpv_output` equals `walker_output`, error lines included."""
    accepted(source)
    assert cbpv_output(source) == walker_output(source)


@pytest.mark.obligation("the interpreter and the compiled program print the same")
@given(recursive())
def test_lower_agrees_recursive(source: str) -> None:
    """[law: lower-agrees-recursive] For every program `recursive()` draws (each draw holds a
    match; recursion terminates by construction), pass 2's output passes `check(loops=False)`,
    and `cbpv_output` equals `walker_output`, error lines included."""
    accepted(source)
    assert cbpv_output(source) == walker_output(source)


def ir_effect(node: object, known: Mapping[str, Effects]) -> Effects:
    """What running `node` may do, read off the IR apart from the lowering's own bookkeeping:
    every `fail`, every `rec`'s and constant's declared effect, and a `force` of an earlier
    definition its effect, over every subterm."""
    match node:
        case Fail():
            own: Effects = frozenset({"fail"})
        case Rec(eff=eff) | Prim(eff=eff):
            own = eff
        case Force(value=Var(name=name)) if name in known:
            own = known[name]
        case _:
            own = frozenset()
    parts = [getattr(node, f.name) for f in fields(node)] if is_dataclass(node) else []
    return own.union(*(ir_effect(part, known) for part in parts))


def called(code: tuple[Node, ...]) -> set[str]:
    """The words a word's code calls, through match rows and their guards."""
    names: set[str] = set()
    for node in code:
        if isinstance(node, Call):
            names.add(node.name)
        elif isinstance(node, Match):
            for row in node.rows:
                names |= called(row.body)
                names |= {p.test for p in row.patterns if isinstance(p, Guarded)}
    return names


def looped(comp: Comp, defs: Mapping[str, Thunk]) -> Rec | None:
    """The `rec` a definition's body is, or projects out of a `force` of."""
    match comp:
        case Rec():
            return comp
        case First(comp=inner) | Second(comp=inner):
            return looped(inner, defs)
        case Force(value=Var(name=name)):
            return looped(defs[name].body, defs)
        case _:
            return None


@given(recursive())
def test_effect_line_sound(source: str) -> None:
    """[law: effect-line-sound] For every program `recursive()` draws: every lowered word whose
    walker effect line has `+fail` has `fail` in its IR effect; every word in a recursive
    component is lowered to a `Rec` (or a projection of one) with `div`; no word outside a
    recursive component and not reaching one has `div`."""
    core = lowered(source)
    program = accepted(source)[0]
    defs = {name: value for name, value in program.defs if isinstance(value, Thunk)}
    known: dict[str, Effects] = {}
    for name, value in program.defs:
        known[name] = ir_effect(value, known)
    defines = {s.name: s for s in core.statements if isinstance(s, Define)}
    looping: set[str] = set()
    for component in core.components:
        calls_of = set[str]().union(*(called(defines[n].code) for n in component))
        own = len(component) > 1 or bool(calls_of & set(component))
        if own or calls_of & looping:
            looping |= set(component)
        for name in component:
            rec = looped(defs[name].body, defs)
            assert not own or (rec is not None and "div" in rec.eff)
            assert name in looping or "div" not in known[name]
            assert "+fail" not in effect_line(defines[name]).items or "fail" in known[name]


@given(controlled(), st.integers(0, 3))
def test_arity_exact(source: str, k: int) -> None:
    """[law: arity-exact] For every literal quotation in a program `controlled()` draws that
    pass 2 accepts, run in place by the walker (`!`) on a stack k values deeper than its input
    count, the walker leaves those k values untouched below exactly the output count pass 2
    computed. A quotation naming a binder is run as the walker holds it once the binder is
    gone, so only closed ones are run; a run the walker refuses has no stack to judge."""
    words = tuple(s for s in desugar(parse(source)) if isinstance(s, Define))
    for origin in accepted(source)[2]:
        if any(substitute(origin.code, x, PROBE) != origin.code for x, _ in origin.names):
            continue
        below = tuple(Push(n) for n in range(k + origin.ins))
        try:
            (after,) = evaluate((*words, Run((*below, Push(Quotation(origin.code)), BANG))))
        except FplError:
            continue
        assert after[:k] == tuple(range(k))
        assert len(after) == k + origin.outs


BANG = Call("!", START)


def test_held_prints_through_a() -> None:
    assert cbpv_output("5 →x ⟨ [ x ] ⟩") == "⟨ [ 5 ] ⟩\n" == walker_output("5 →x ⟨ [ x ] ⟩")


def test_binder_named_as_a_word_is_refused() -> None:
    refused = cbpv_output("[ dup ] →x 2 →dup x !")
    assert isinstance(refused, Refused)
    assert refused.kind == RefusalKind.BINDER_CAPTURES


def test_control_word_violates_straight_line() -> None:
    with pytest.raises(icontract.ViolationError):
        polarise(lowered("1 [ 2 ] [ 3 ] if"))


def test_in_place_below_the_stack_is_an_effect_mismatch() -> None:
    refused = polarise(lowered("[ + ] !"))
    assert isinstance(refused, Refused)
    assert refused.kind == RefusalKind.EFFECT_MISMATCH


@pytest.mark.parametrize(
    ("source", "kind"),
    [
        ("⟨ 1 2 ⟩ [ dup ] each", RefusalKind.STEP_ARITY),
        ("⟨ 1 2 ⟩ [ + ] each", RefusalKind.EFFECT_MISMATCH),
        ("[ ⟨ 1 ⟩ [ drop drop drop ] fold ]", RefusalKind.EFFECT_MISMATCH),
    ],
)
def test_a_step_off_one_value_is_refused(source: str, kind: RefusalKind) -> None:
    refused = polarise(lowered(source))
    assert isinstance(refused, Refused)
    assert refused.kind == kind


def test_forcing_walker_data_is_a_quotation_unknown() -> None:
    source = source_of((word("g", 1, 0, BANG), Run((Push(1), Call("g", START)))))
    refused = cbpv_output(source)
    assert isinstance(refused, Refused)
    assert refused.kind == RefusalKind.QUOTATION_UNKNOWN


# Quotations: boxed into `+`, run in place, read back as sections and closures, passed to
# words, pairs and dicts, and the walker's own error for an operand that is no quotation.
QUOTING = (
    "[ 1 ] 2 +",
    "1 | 2 [ + ] !",
    "1 [ drop ] !",
    "1 | 2 [ - ] swap-args",
    "1 2 3 +",
    "5 →x [ x 1 + ]",
    "[ 2 ] →q [ q ! ] !",
    "[ 2 ] →q ⟨ [ q ] ⟩",
    "[ [ 1 ] ] ! !",
    "[ dup ] →d 3 d !",
    "[ 1 ] dup pair",
    "1 !",
    "1 | 2 | 3 swap-args",
    "f : i -- o\n[ 1 ] f\n",
    "[ 1 ] →a { k a }\n",
    "1 2 3 [ 1 + ] each",
    "1 2 3 [ + ] fold",
    "1 2 3 [ + ] scan",
    "⟨ ⟩ [ + ] fold",
    "⟨ ⟩ [ + ] scan",
    "1 [ + ] fold",
    "⟨ 1 2 ⟩ 3 each",
    "⟨ 1 [ 2 ] ⟩ [ 1 + ] each",
    "⟨ 1 2 ⟩ [ drop [ 1 ] ] each",
    "[ ⟨ 1 2 ⟩ [ 1 + ] each ] !",
    "⟨ 1 2 ⟩ [ 1 + ] →q q each",
)


@pytest.mark.parametrize("source", QUOTING)
def test_each_quotation_agrees(source: str) -> None:
    accepted(source)
    assert cbpv_output(source) == walker_output(source)


def word(name: str, ins: int, outs: int, *code: Push | Call | Bind | Keyed | Match) -> Define:
    effect = Effect(tuple(f"i{k}" for k in range(ins)), tuple(f"o{k}" for k in range(outs)))
    return Define(name, effect, code)


def calls(*names: str) -> tuple[Call, ...]:
    return tuple(Call(n, START) for n in names)


def bind(name: str, *code: Push | Call | Bind | Keyed) -> Bind:
    return Bind(name, code, START)


QUOTED = Push(Listed((Quotation(calls("a")), Quotation(calls("b")))))
DICT = Keyed((("k", Push(1)), ("m", Call("a", START))), START)
# One program per construct polarise lowers, so no branch waits on a random draw.
PROGRAMS = {
    "builtins": (Run((Push(1), *calls("dup", "+", "dup", "swap", "drop", "dup", "pair"))),),
    "panic": (Run((Push(Listed(())), Push(1), *calls("+"))),),
    "binders": (Run((Push(1), Push(2), bind("a", bind("b", QUOTED, *calls("b", "a"))))),),
    "shadow": (Run((Push(1), bind("a", Push(2), bind("a", Push(Quotation(calls("a"))))))),),
    "dict": (Run((Push(3), bind("a", DICT))),),
    "infer": (Run((Push(1), Push(2), *calls("_", "+"))), Run(calls("_"))),
    "goal": (Run((Push(1), *calls("?", "dup"))),),
    "words": (
        word("f", 1, 2, Push(1), *calls("+", "dup")),
        word("g", 0, 0),
        Run((Push(2), *calls("f", "g", "f/doc", "f/effect"))),
    ),
}


@pytest.mark.parametrize("name", sorted(PROGRAMS))
def test_each_construct_agrees(name: str) -> None:
    source = source_of(PROGRAMS[name])
    accepted(source)
    assert cbpv_output(source) == walker_output(source)


GUARD = "g : v -- b\n\tmatch\n\t\t2\t1\n\t\t_\t0\n"
# Matches: no row at the root, literals equal as the walker's (1 and 1.0), names, $x, guards
# (the guard run although its pattern failed, and failing inside), a fail through `each`.
MATCHING = (
    "f : x -- y\n\tmatch\n\t\t0\t1\n5 f\n",
    "f : x -- y\n\tmatch\n\t\t0\t1\n\t\t_\t8\n0 f\n3 f\n",
    "f : x -- y\n\tmatch\n\t\t1.0\t7\n\t\t_\t8\n1 f\n",
    "f : x -- y\n\tmatch\n\t\tx\tx 1 +\n4 f\n",
    "f : a n -- r\n\tmatch\n\t\t1\t2\t5\n\t\t_\t_\t6\n1 | 2 f\n1 | 3 f\n2 | 2 f\n",
    f"{GUARD}f : a n -- r\n\tmatch\n\t\t_\t0\t7\n\t\tx\t$x\tx\n\t\t_\tn ∈ g\tn\n"
    "\t\tx\tn\t9\n3 | 3 f\n5 | 2 f\n1 | 3 f\n",
    f"{GUARD}f : v -- r\n\tmatch\n\t\t0 ∈ g\t1\n\t\t_\t2\n0 f\n2 f\n",
    "g : v -- b\n\tmatch\n\t\t2\t1\nf : v -- r\n\tmatch\n\t\tn ∈ g\t1\n\t\t_\t0\n2 f\n3 f\n",
    "f : x -- y\n\tmatch\n\t\t0\t1\n⟨ 0 5 ⟩ [ f ] each\n",
)


@pytest.mark.parametrize("source", MATCHING)
def test_each_match_agrees(source: str) -> None:
    accepted(source)
    assert cbpv_output(source) == walker_output(source)


def test_no_row_matching_fails_with_the_walkers_error() -> None:
    assert cbpv_output(MATCHING[0]) == "ERROR: 2:2 no row matches" == walker_output(MATCHING[0])


COUNTDOWN = "f : n -- r\n\tmatch\n\t\t0\t0\n\t\tn\tn 1 - f 1 +\n3 f\n0 f\n"
EVEN_ODD = (
    "even : n -- b\n\tmatch\n\t\t0\t1\n\t\tn\tn 1 - odd\n"
    "odd : n -- b\n\tmatch\n\t\t0\t0\n\t\tn\tn 1 - even\n"
    "use : n -- b\n\tmatch\n\t\tn\tn even\n"
    "3 even\n2 even\n3 odd\n2 use\n"
)
# A word reaching itself through a quotation, a group of three, and a thunk left by a
# recursive word, boxed on the way out.
RECURRING = (
    COUNTDOWN,
    EVEN_ODD,
    "f : n -- r\n\tmatch\n\t\t0\t0\n\t\tn\tn 1 - [ f ] ! 1 +\n2 f\n",
    "a : n -- r\n\tmatch\n\t\t0\t0\n\t\tn\tn 1 - b\n"
    "b : n -- r\n\tmatch\n\t\t0\t1\n\t\tn\tn 1 - c\n"
    "c : n -- r\n\tmatch\n\t\t0\t2\n\t\tn\tn 1 - a\n4 a\n5 b\n",
    "f : n -- r q\n\tmatch\n\t\t0\t0\n\t\tn\tn 1 - f drop\n\t[ 7 ]\n2 f\n",
)


@pytest.mark.parametrize("source", RECURRING)
def test_each_recursion_agrees(source: str) -> None:
    accepted(source)
    assert cbpv_output(source) == walker_output(source)


def test_a_countdown_and_an_even_odd_pair_run_as_the_walker() -> None:
    assert cbpv_output(COUNTDOWN) == "3\n0\n" == walker_output(COUNTDOWN)
    assert cbpv_output(EVEN_ODD) == "0\n1\n1\n1\n" == walker_output(EVEN_ODD)


@given(broad_match())
def test_refusal_named_match(source: str) -> None:
    """[law: refusal-named-match] On every program `broad_match()` draws (each draw holds an
    inverse pattern or rows that leave different shapes), the lowering either refuses with a
    `RefusalKind` and a span inside the source, or its output equals the walker's; it never
    raises."""
    output = cbpv_output(source)
    if isinstance(output, Refused):
        lines = source.splitlines()
        assert isinstance(output.kind, RefusalKind)
        assert 1 <= output.at.line <= len(lines)
        assert 1 <= output.at.col <= len(lines[output.at.line - 1])
    else:
        assert output == walker_output(source)


def test_an_inverse_pattern_is_refused_where_it_is_written() -> None:
    refused = cbpv_output("k : v -- r\n\tmatch\n\t\t( cons x xs )\tx\n\t\t_\t0\n⟨ 1 ⟩ k\n")
    assert isinstance(refused, Refused)
    assert (refused.kind, refused.at.line) == (RefusalKind.INVERSE_PATTERN, 3)


def refusal(core: CoreA) -> RefusalKind:
    refused = polarise(core)
    assert isinstance(refused, Refused)
    return refused.kind


ZERO = Equal(Push(0))


@pytest.mark.parametrize(
    ("source", "kind"),
    [
        ("f : x -- y\n\tmatch\n\t\t0\t1\n\t\t_\t#z\n0 f\n", RefusalKind.BRANCHES_DISAGREE),
        ("f : x -- y\n\tmatch\n\t\tx ∈ dup\t1\n\t\t_\t0\n0 f\n", RefusalKind.EFFECT_MISMATCH),
    ],
)
def test_a_match_off_one_shape_is_refused(source: str, kind: RefusalKind) -> None:
    assert refusal(lowered(source)) == kind


def test_core_a_match_off_its_rules_is_refused() -> None:
    """Rows no surface program writes: leaving different counts, reaching below the match, and
    an inverse pattern pass 1 would have refused."""
    uneven = Match((Row((ZERO,), (Push(1), Push(2))), Row((Wild(),), (Push(3),))), START)
    below = Match((Row((Wild(),), calls("+")),), START)
    inverse = Match((Row((Inverse("pair", (Wild(),), START),), ()),), START)
    for code, kind in (
        (uneven, RefusalKind.BRANCHES_DISAGREE),
        (below, RefusalKind.EFFECT_MISMATCH),
        (inverse, RefusalKind.INVERSE_PATTERN),
    ):
        core = CoreA((word("f", 2, 1, code), Run((Push(1), Push(2), *calls("f")))), (("f",),))
        assert refusal(core) == kind


def test_a_recursive_body_off_its_outputs_is_refused() -> None:
    """07 refuses such a body; a `rec` at `Dyn` outputs cannot return it."""
    core = CoreA((word("f", 1, 1, *calls("f", "dup")), Run((Push(1), *calls("f")))), (("f",),))
    assert refusal(core) == RefusalKind.EFFECT_MISMATCH
