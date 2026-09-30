"""Pass 2 on straight-line code: the compiled program prints what the walker prints."""

import icontract
import pytest
from hypothesis import given
from hypothesis import strategies as st
from lower_diff import cbpv_output, walker_output
from lower_strategies import START, controlled, source_of, straight

from fpl.ast_core import Bind, Call, Define, Effect, Keyed, Listed, Push, Quotation, Run
from fpl.cbpv.check import check
from fpl.desugar import desugar
from fpl.errors import FplError
from fpl.eval import evaluate, substitute
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


def word(name: str, ins: int, outs: int, *code: Push | Call | Bind | Keyed) -> Define:
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
