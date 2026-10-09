"""A session is its accepted inputs run again as one file; only the new input's output shows."""

from collections.abc import Sequence
from dataclasses import replace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fpl import session
from fpl.ast_core import EFFECTS
from fpl.driver import run
from fpl.errors import FplError, Span
from fpl.log import SCHEMA, Event, Log, RefusedError
from fpl.multihash import BLAKE2B_256, content
from fpl.session import FUEL_DEFAULT, Context, Outcome, enter, evaluator, program, rewind, words

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


def entered(texts: Sequence[str], log: Log = EMPTY) -> tuple[Log, tuple[Outcome, ...]]:
    """The log after each text is entered at the head, and each outcome."""
    outcomes: list[Outcome] = []
    for text in texts:
        outcome = enter(log, text, CONTEXT, log.head)
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
    assert enter(log, "f\n", CONTEXT, log.head).notes == outcomes[2].notes


def test_an_error_in_an_earlier_input_names_its_event() -> None:
    texts = ["g : x -- y\n\tdup drop\n", "f : x -- y\n\tg\n", "g : x -- y y\n\tdup\n"]
    _, outcomes = entered(texts)
    last = outcomes[2]
    assert last.out == "ERROR: @2 1:1 f leaves 2 values, its effect line 1\n"
    assert last.notes == ("f : x -- y\n^",)
    assert last.event.status == "error"
    assert last.bodies[last.event.out] == last.out.encode()


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


def defined(texts: Sequence[str]) -> list[str]:
    """The lines of the words the program of `texts` defines, after the builtins' block."""
    log, _ = entered(texts)
    return words(log, log.head).partition("\n\n")[2].splitlines()


def test_the_words_are_the_builtins_then_the_definitions() -> None:
    log, _ = entered(["plus-one : n -- n\n\t1 +\n"])
    builtins, rest = words(log, log.head).split("\n\n")
    lines = builtins.splitlines()
    assert [line.split(" : ")[0] for line in lines] == sorted(EFFECTS)
    assert lines[:3] == ["! : q -- x", "+ : x y -- z", ", : a b -- ab"]
    assert {"each : xs q -- ys", "fold : xs q -- x", "swap : x y -- y x"} <= set(lines)
    assert rest == "plus-one : n -- n\n"


def test_a_state_that_defines_nothing_has_no_second_block() -> None:
    nothing = words(EMPTY, None)
    assert nothing.endswith("\n")
    assert "\n\n" not in nothing
    log, _ = entered(["1 2 +\n", "1 [\n"])
    assert words(log, log.head) == nothing


def test_the_words_of_an_earlier_state() -> None:
    log, (first, _, _) = entered(["a : -- x\n\t1\n", "b : -- x\n\t2\n", "c : -- x\n\t1 ["])
    assert words(log, log.head).endswith("\n\na : -- x\nb : -- x\n")
    assert words(log, first.event).endswith("\n\na : -- x\n")
    assert words(log, None) == words(EMPTY, None)


def test_the_words_are_sorted_and_the_later_definition_is_in_force() -> None:
    texts = ["b : -- x\n\t1\n", "a : n -- n\n\t1 +\n", "b : -- y\n\t2\n"]
    assert defined(texts) == ["a : n -- n", "b : -- y"]


def test_a_dispatched_word_is_its_clauses_in_the_order_written() -> None:
    texts = ["f : x: Text -- y\n\tdrop 2\n", "f : x: Int -- y\n\tdrop 1\n", "g : -- x\n\t1\n"]
    assert defined(texts) == ["f : x: Text -- y", "f : x: Int -- y", "g : -- x"]


def test_a_head_group_is_listed_once_without_the_tests_made_for_it() -> None:
    shapes = "circle : r -- shape\n\t#circle swap pair\n"
    lines = defined([shapes, "area : ( circle r ) -- n\n\tr dup times\n"])
    assert [line.split(" : ")[0] for line in lines] == ["area", "circle"]
    assert lines[0].endswith(" -- n +fail")


@pytest.mark.parametrize(
    ("source", "word"),
    [
        ("plus-one : n -- n\n\t1 +\n", "plus-one"),
        ("f : x -- c\n\tmatch\n\t\t1\t#one\n", "f"),
        ("d/\n\tg : -- x\n\t\t1\n", "d/g"),
    ],
)
def test_a_listed_effect_is_what_the_effect_query_pushes(source: str, word: str) -> None:
    """The text after the colon is the strings w/effect answers, joined by spaces."""
    (line,) = defined([source])
    assert line.startswith(f"{word} : ")
    strings = " ".join(f"“{each}”" for each in line.removeprefix(f"{word} : ").split())
    assert run(f"{source}{word}/effect\n") == run(f"⟨ {strings} ⟩\n")


def test_a_program_that_no_longer_checks_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    log, _ = entered(["1\n"])

    def changed(_source: str) -> None:
        raise FplError(Span(2, 3), "no longer so")

    monkeypatch.setattr(session, "checked", changed)
    with pytest.raises(RefusedError, match=r"^the program does not check: 2:3 no longer so$"):
        words(log, log.head)


def test_a_name_written_with_a_prime_is_listed() -> None:
    """A prime is legal in a name; only the dispatchers and the tests made for a head group
    are left out, and a name beside the group clause `area` that holds one is neither."""
    prime = "\N{PRIME}"
    shapes = "circle : r -- shape\n\t#circle swap pair\n"
    group = "area : ( circle r ) -- n\n\tr dup times\n"
    texts = [f"foo{prime} : -- x\n\t1\n", f"d{prime}/\n\tg : -- x\n\t\t1\n", shapes, group]
    names = [line.split(" : ")[0] for line in defined([*texts, f"area{prime} : -- x\n\t1\n"])]
    assert names == ["area", f"area{prime}", "circle", f"d{prime}/g", f"foo{prime}"]


def test_a_clause_under_the_path_of_a_made_test_is_listed() -> None:
    """A clause written under the path that names a test made for a head group has a longer
    word than the test, is what that path calls, and is listed."""
    prime = "\N{PRIME}"
    shapes = "circle : r -- shape\n\t#circle swap pair\n"
    group = "area : ( circle r ) -- n\n\tr dup times\n"
    clause = f"area/\n\t1/\n\t\t1{prime}1 : x: Int -- y\n\t\t\tdrop 7\n"
    assert run(f"{shapes}{group}{clause}3 area/1/1{prime}1\n") == run("7\n")
    lines = defined([shapes, group, clause])
    assert [line.split(" : ")[0] for line in lines] == ["area", f"area/1/1{prime}1", "circle"]
    assert lines[1] == f"area/1/1{prime}1 : x: Int -- y"


def test_a_definition_that_shadows_a_builtin_takes_its_place_in_the_listing() -> None:
    """The word in force is the definition, so its line is listed once, in the session's block,
    and the builtin's is not; a definition under a directory shadows nothing."""
    log, _ = entered(["+ : x -- y\n\t2 times\n", "d/\n\ttimes : x -- y\n\t\tdrop 2\n"])
    builtins, rest = words(log, log.head).split("\n\n")
    lines = builtins.splitlines()
    assert "+ : x y -- z" not in lines
    assert "times : x y -- z" in lines
    assert len(lines) == len(EFFECTS) - 1
    assert rest == "+ : x -- y\nd/times : x -- y\n"


@pytest.mark.parametrize(("before", "answer", "listed"), [(False, "7", True), (True, "0", False)])
def test_a_definition_at_the_word_of_a_made_test_is_listed_while_it_is_in_force(
    before: bool, answer: str, listed: bool
) -> None:
    """Untyped, a clause at the path of a test made for a head group has that test's word; the
    later of the two is what the word calls, and the user's is listed only when it is that one."""
    prime = "\N{PRIME}"
    shapes = "circle : r -- shape\n\t#circle swap pair\n"
    group = "area : ( circle r ) -- n\n\tr dup times\n"
    clause = f"area/\n\t1/\n\t\t1{prime}1 : x -- b\n\t\t\tdrop 7\n"
    texts = [shapes, clause, group] if before else [shapes, group, clause]
    assert run(f"{''.join(texts)}3 area/1/1{prime}1\n") == run(f"{answer}\n")
    expected = ["area", f"area/1/1{prime}1", "circle"] if listed else ["area", "circle"]
    assert [line.split(" : ")[0] for line in defined(texts)] == expected
