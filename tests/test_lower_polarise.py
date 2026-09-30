"""Pass 2 on straight-line code: the compiled program prints what the walker prints."""

import icontract
import pytest
from hypothesis import given
from lower_diff import cbpv_output, walker_output
from lower_strategies import START, source_of, straight

from fpl.ast_core import Bind, Call, Define, Effect, Keyed, Listed, Push, Quotation, Run
from fpl.cbpv.check import check
from fpl.desugar import desugar
from fpl.lower.polarise import polarise
from fpl.lower.select import CoreA, RefusalKind, Refused, select
from fpl.lower.walker import signature
from fpl.parse import parse


def lowered(source: str) -> CoreA:
    core = select(desugar(parse(source)))
    assert isinstance(core, CoreA)
    return core


@pytest.mark.obligation("the interpreter and the compiled program print the same")
@given(straight())
def test_lower_agrees_straight(source: str) -> None:
    """[law: lower-agrees-straight] For every program `straight()` draws, pass 2's output
    passes `check(loops=False)`, and `cbpv_output` equals `walker_output`: the same printed
    stacks, or the same error line."""
    program, extra = polarise(lowered(source))
    assert check(program, signature(extra), loops=False) is None
    assert cbpv_output(source) == walker_output(source)


def test_held_prints_through_a() -> None:
    assert cbpv_output("5 →x ⟨ [ x ] ⟩") == "⟨ [ 5 ] ⟩\n" == walker_output("5 →x ⟨ [ x ] ⟩")


def test_binder_named_as_a_word_is_refused() -> None:
    refused = cbpv_output("[ dup ] →x 2 →dup x !")
    assert isinstance(refused, Refused)
    assert refused.kind == RefusalKind.BINDER_CAPTURES


def test_control_word_violates_straight_line() -> None:
    with pytest.raises(icontract.ViolationError):
        polarise(lowered("1 [ dup ] !"))


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
    program, extra = polarise(lowered(source))
    assert check(program, signature(extra), loops=False) is None
    assert cbpv_output(source) == walker_output(source)
