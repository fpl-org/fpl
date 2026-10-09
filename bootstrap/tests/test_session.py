"""A session is its accepted inputs run again as one file; only the new input's output shows."""

from collections.abc import Sequence
from dataclasses import replace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fpl import session
from fpl.driver import run
from fpl.errors import FplError, Span
from fpl.log import SCHEMA, Event, Log, RefusedError
from fpl.multihash import BLAKE2B_256, content
from fpl.session import FUEL_DEFAULT, Context, Outcome, enter, evaluator, program, rewind

CONTEXT = Context(evaluator(), "agent", "Claude Opus 5.5", "s", FUEL_DEFAULT)
EMPTY = Log((), {}, 0)
POOL = (
    "1\n",
    "x\n",
    "1 [\n",
    "f : -- x\n\t2\n",
    "f\n",
    "g : x -- y\n\t?\n",
    "1 g\n",
    "\t3\n",
    "\n",
)


def grown(log: Log, outcome: Outcome) -> Log:
    """The in-memory log after the outcome's event."""
    return log.grown(outcome.event, outcome.bodies, log.size)


def entered(
    texts: Sequence[str], log: Log = EMPTY, context: Context = CONTEXT
) -> tuple[Log, tuple[Outcome, ...]]:
    """The log after each text is entered at the head, and each outcome."""
    outcomes: list[Outcome] = []
    for text in texts:
        outcome = enter(log, text, context, log.head)
        outcomes.append(outcome)
        log = grown(log, outcome)
    return log, tuple(outcomes)


@st.composite
def definitions_then_uses(draw: st.DrawFn) -> list[str]:
    """Inputs that each define a fresh name or run lines of numbers and names defined before."""
    inputs: list[str] = []
    names: list[str] = []
    for i in range(draw(st.integers(1, 5))):
        if draw(st.booleans()):
            inputs.append(f"w{i} : -- x\n\t{draw(st.integers(0, 9))}\n")
            names.append(f"w{i}")
            continue
        words = st.lists(st.sampled_from([*names, "1", "23"]), min_size=1, max_size=3)
        lines = draw(st.lists(words.map(" ".join), min_size=1, max_size=2))
        inputs.append("".join(line + "\n" for line in lines))
    return inputs


@given(definitions_then_uses())
def test_a_session_prints_what_its_file_prints(inputs: list[str]) -> None:
    """[law: repl-is-file] for inputs that define distinct names used only after their
    definition, the joined per-input outputs equal run of the joined inputs."""
    _, outcomes = entered(inputs)
    assert all(o.event.status == "ok" for o in outcomes)
    assert "".join(o.out for o in outcomes) == run("".join(inputs))


@st.composite
def histories(draw: st.DrawFn) -> Log:
    """A log of inputs from the pool, with rewinds to earlier events among them."""
    log = EMPTY
    for _ in range(draw(st.integers(1, 6))):
        back = draw(st.integers(0, len(log.events)))
        if back < len(log.events) and draw(st.booleans()):
            target = log.events[back - 1] if back else None
            log = log.grown(rewind(log, target, CONTEXT), {content(b""): b""}, log.size)
        else:
            log = grown(log, enter(log, draw(st.sampled_from(POOL)), CONTEXT, log.head))
    return log


def parent(log: Log, event: Event) -> Event | None:
    """The event whose state `event` extends."""
    return next((e for e in log.events if (e.ident,) == event.deps), None)


@given(histories())
def test_a_cut_log_holds_the_same_programs(log: Log) -> None:
    """[law: prefix-stability] the program at event k from the log cut at k equals the program
    at k from the full log; an error event's program equals its parent's."""
    for k, event in enumerate(log.events, 1):
        cut = Log(log.events[:k], log.bodies, log.size)
        assert program(cut, event) == program(log, event)
        if event.status == "error":
            assert program(log, event) == program(log, parent(log, event))


@given(st.lists(st.sampled_from(POOL), min_size=1, max_size=5), st.data())
def test_a_rewind_returns_to_its_target(texts: list[str], data: st.DataObject) -> None:
    """[law: rewind] after a rewind to e the program equals the program at e; the abandoned
    head's program is unchanged; the next input's output equals an as-of evaluation at e."""
    before, _ = entered(texts)
    head = before.head
    target = data.draw(st.sampled_from((None, *before.events[:-1])))
    event = rewind(before, target, CONTEXT)
    after = before.grown(event, {content(b""): b""}, before.size)
    assert program(after, event) == program(after, target)
    assert program(after, head) == program(before, head)
    text = data.draw(st.sampled_from(POOL))
    assert enter(after, text, CONTEXT, event).out == enter(before, text, CONTEXT, target).out


def test_an_earlier_input_whose_output_moved_is_named() -> None:
    log, outcomes = entered(["f : -- x\n\t1\n", "f\n", "f : -- x\n\t2"])
    second = outcomes[1].event
    assert [o.out for o in outcomes] == ["", "1\n", ""]
    assert outcomes[2].notes == (f"CHANGED 2 ${second.ident.spelled()}",)
    assert outcomes[2].bodies[outcomes[2].event.body] == b"f : -- x\n\t2\n"
    assert enter(log, "f\n", CONTEXT, log.head).notes == ()


def test_a_redefinition_is_named_once_not_after_every_later_input() -> None:
    define = "plus-one : n -- n\n\t{} +\n"
    _, outcomes = entered([define.format(1), "3 plus-one\n", define.format(2), "1\n", "2\n"])
    assert [o.out for o in outcomes] == ["", "4\n", "", "1\n", "2\n"]
    assert [o.notes for o in outcomes] == [
        (),
        (),
        (f"CHANGED 2 ${outcomes[1].event.ident.spelled()}",),
        (),
        (),
    ]


def test_an_output_that_moves_back_is_named_again() -> None:
    texts = ["f : -- x\n\t1\n", "f\n", "f : -- x\n\t2\n", "f : -- x\n\t1\n"]
    _, outcomes = entered(texts)
    named = (f"CHANGED 2 ${outcomes[1].event.ident.spelled()}",)
    assert [o.notes for o in outcomes] == [(), (), named, named]


def test_a_baseline_runs_under_the_fuel_its_program_was_accepted_with() -> None:
    """The program before an input may need more fuel than this call has; the input that
    redefines the costly word still succeeds, and names the output it moves."""
    log, outcomes = entered(["f : -- x\n\t1 | 1 +\n", "f\n"], context=replace(CONTEXT, fuel=100))
    low = replace(CONTEXT, fuel=2)
    assert enter(log, "f\n", low, log.head).out == "ERROR: @2 1:1 out of fuel\n"
    outcome = enter(log, "f : -- x\n\t3\n", low, log.head)
    assert (outcome.event.status, outcome.out) == ("ok", "")
    assert outcome.notes == (f"CHANGED 2 ${outcomes[1].event.ident.spelled()}",)


def test_a_baseline_that_fails_refuses_nothing() -> None:
    """A program that no longer runs within the fuel it was accepted with (written under
    another evaluator) is not compared: the input that redefines the costly word still
    succeeds, and names nothing."""
    log, _ = entered(["f : -- x\n\t1 | 1 +\n"], context=replace(CONTEXT, fuel=100))
    run = enter(log, "f\n", replace(CONTEXT, fuel=100), log.head)
    log = grown(log, replace(run, event=replace(run.event, fuel=2)))
    outcome = enter(log, "f : -- x\n\t3\n", replace(CONTEXT, fuel=2), log.head)
    assert (outcome.event.status, outcome.out, outcome.notes) == ("ok", "", ())


def test_a_baseline_that_ran_within_less_fuel_still_names_what_moved() -> None:
    log, outcomes = entered(["f : -- x\n\t2\n", "f\n"], context=replace(CONTEXT, fuel=2))
    outcome = enter(log, "f : -- x\n\t1 | 2 +\n", replace(CONTEXT, fuel=100), log.head)
    assert (outcome.event.status, outcome.out) == ("ok", "")
    assert outcome.notes == (f"CHANGED 2 ${outcomes[1].event.ident.spelled()}",)


@given(st.lists(st.sampled_from(("f : -- x\n\t1\n", "f : -- x\n\t2\n", "f\n")), max_size=6))
def test_a_blank_input_moves_no_output(texts: list[str]) -> None:
    """[law: changed-once] nothing is named after an input that adds no line, whatever was
    defined again before it."""
    log, _ = entered(texts)
    assert enter(log, "\n", CONTEXT, log.head).notes == ()


def test_an_error_in_an_earlier_input_names_its_event() -> None:
    texts = ["g : x -- y\n\tdup drop\n", "f : x -- y\n\tg\n", "g : x -- y y\n\tdup\n"]
    _, outcomes = entered(texts)
    last = outcomes[2]
    assert last.out == "ERROR: @2 1:1 f leaves 2 values, its effect line 1\n"
    assert last.notes == ("f : x -- y\n^",)
    assert last.event.status == "error"
    assert last.bodies[last.event.out] == last.out.encode()


def test_an_unknown_word_is_told_at_the_word_in_the_input_that_holds_it() -> None:
    log, outcomes = entered(["2 | 3 +\n", "foo\n", "f : -- x\n\t2\n", "f gone\n", "f\n"])
    assert [o.out for o in outcomes] == [
        "5\n",
        "ERROR: 1:1 unknown word: foo\n",
        "",
        "ERROR: 1:3 unknown word: gone\n",
        "2\n",
    ]
    assert [o.notes for o in outcomes] == [(), ("foo\n^",), (), ("f gone\n  ^",), ()]
    assert [o.event.status for o in outcomes] == ["ok", "error", "ok", "error", "ok"]
    assert [part.text for part in program(log, log.head)] == ["2 | 3 +\n", "f : -- x\n\t2\n", "f\n"]


def test_a_word_the_language_knows_but_no_evaluator_runs_is_told_apart() -> None:
    _, outcomes = entered(["1 2 +\n", "3 debug\n", "3 gone\n"])
    assert [o.out for o in outcomes[1:]] == [
        "ERROR: 1:3 no evaluator yet: debug\n",
        "ERROR: 1:3 unknown word: gone\n",
    ]
    assert [o.notes for o in outcomes[1:]] == [("3 debug\n  ^",), ("3 gone\n  ^",)]


def test_an_input_after_the_first_starts_at_the_left_margin() -> None:
    _, outcomes = entered(["1\n", "\n\t\n\t3\n", "\n", "\t3\n"])
    assert [o.out for o in outcomes] == [
        "1\n",
        "ERROR: 3:1 an input starts at the left margin\n",
        "",
        "ERROR: 1:1 an input starts at the left margin\n",
    ]
    assert outcomes[1].notes == ("\t3\n^",)


def test_the_first_input_is_its_own_file() -> None:
    _, (outcome,) = entered(["\t1 2 +\n"])
    assert outcome.out == run("\t1 2 +\n")


def test_goals_are_noted_before_the_run_fails() -> None:
    log, outcomes = entered(["g : x -- y\n\t?\n", "1 g\n", "1 [\n"])
    assert outcomes[0].notes == ("GOAL 2:2 ? : t0 -- value",)
    assert outcomes[1].out == "ERROR: @1 2:2 unfilled goal\n"
    assert outcomes[1].notes == ("\t?\n ^",)
    assert outcomes[2].out == "ERROR: 1:3 [ never closed\n"
    assert outcomes[2].notes == ("1 [\n  ^",)
    assert program(log, log.head) == program(log, outcomes[0].event)


def test_an_error_past_the_input_has_no_caret(monkeypatch: pytest.MonkeyPatch) -> None:
    def past(source: str) -> None:
        raise FplError(Span(source.count("\n") + 1, 1), "cut short")

    monkeypatch.setattr(session, "checked", past)
    outcome = enter(EMPTY, "1", CONTEXT, None)
    assert (outcome.out, outcome.notes) == ("ERROR: 2:1 cut short\n", ())


def test_a_rewind_names_its_target_and_the_head_it_leaves() -> None:
    log, (first, second) = entered(["1\n", "2\n"])
    event = rewind(log, None, CONTEXT)
    assert (event.kind, event.seq, event.deps, event.links) == (
        "rewind",
        3,
        (),
        (second.event.ident,),
    )
    assert rewind(log, first.event, CONTEXT).deps == (first.event.ident,)
    assert (event.schema, event.fuel, event.body, event.out) == (
        SCHEMA,
        FUEL_DEFAULT,
        content(b""),
        content(b""),
    )


@pytest.mark.parametrize(
    ("texts", "message"), [([], "nothing to rewind"), (["1\n"], "cannot rewind to the head")]
)
def test_a_rewind_is_refused_where_it_would_change_nothing(texts: list[str], message: str) -> None:
    log, _ = entered(texts)
    with pytest.raises(RefusedError, match=message):
        rewind(log, log.head, CONTEXT)


def test_the_evaluator_is_the_hash_of_its_sources_once() -> None:
    assert evaluator() is evaluator()
    assert evaluator().code == BLAKE2B_256
    assert replace(CONTEXT, fuel=3).fuel == 3
    assert (CONTEXT.who, CONTEXT.model, CONTEXT.session) == ("agent", "Claude Opus 5.5", "s")
