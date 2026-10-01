"""Pass 3, label: a label at every definition entry, `Rec` body and loop body, and nothing
else changed (design section 6.4)."""

from hypothesis import given
from lower_diff import Ran, ended, lowered, ran
from lower_strategies import walker_programs

from fpl.cbpv.check import check
from fpl.cbpv.machine import Event, LabelEvent
from fpl.cbpv.syntax import Base, Const, Label, Program, Thunk
from fpl.lower.label import label
from fpl.lower.walker import signature


@given(walker_programs())
def test_labels_per_loop(source: str) -> None:
    """[law: labels-per-loop] Every program pass 3 emits for a program `walker_programs()`
    draws passes `check(loops=True)`, with a label at every definition entry, `Rec` body and
    loop body."""
    result = lowered(source)
    assert isinstance(result, tuple), result
    program, extra, _ = result
    sig = signature(extra)
    labelled = label(program, sig)
    assert check(labelled, sig, loops=True) is None
    assert all(isinstance(v, Thunk) and isinstance(v.body, Label) for _, v in labelled.defs)


def unlabelled(trace: tuple[Event, ...]) -> tuple[Event, ...]:
    return tuple(e for e in trace if not isinstance(e, LabelEvent))


@given(walker_programs())
def test_label_pass_preserves(source: str) -> None:
    """[law: label-pass-preserves] For every program `walker_programs()` draws, the outcome
    after pass 3 equals the outcome after pass 2, and the trace after pass 3 with its labels
    removed equals the trace after pass 2."""
    before, after = ran(source, labelled=False), ran(source)
    assert isinstance(before, Ran), before
    assert isinstance(after, Ran), after
    assert [ended(r, before.origins) for r in before.runs] == [
        ended(r, after.origins) for r in after.runs
    ]
    assert [r.trace for r in before.runs] == [unlabelled(r.trace) for r in after.runs]


def keys(source: str) -> list[list[tuple[str, int]]]:
    """Each run's labels in order, as (word, ordinal)."""
    result = ran(source)
    assert isinstance(result, Ran), result
    return [
        [(e.label.word, e.label.ordinal) for e in r.trace if isinstance(e, LabelEvent)]
        for r in result.runs
    ]


COUNTDOWN = "c : a n -- r\n\tmatch\n\t\t_\t0\t0\n\t\tx\tn\tx n 1 - c\n"


def test_a_fold_and_a_countdown_label_each_pass() -> None:
    """A fold over three items steps twice, each step entering the loop body of its line; a
    countdown from 3 enters `c` once and its `Rec` body four times, at 3, 2, 1 and 0."""
    source = f"1 2 3 [ + ] fold\n{COUNTDOWN}0 | 3 c\n"
    assert keys(source) == [[("line 1", 0)] * 2, [("c", 0)] + [("c", 1)] * 4]


def test_a_mutual_pair_labels_each_component() -> None:
    """`f` enters its projection, then the group's definition, then the group's `Rec`, whose
    components `f` and `h` are labelled 1 and 2 under the group's name."""
    rows = "\tmatch\n\t\t_\t0\t0\n\t\tx\tn\tx n 1 - "
    source = f"f : a n -- r\n{rows}h\nh : a n -- r\n{rows}f\n0 | 2 f\n"
    group = [(" v0", 0), (" v0", 1), (" v0", 2), (" v0", 1)]
    assert keys(source) == [[("f", 0), *group]]


def test_a_definition_not_a_thunk_is_only_walked() -> None:
    program = Program((("c", Const(1, Base("Num"))),), ())
    assert label(program, signature()) == program
