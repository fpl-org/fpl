"""Elaboration: each word's effect inferred from its body and checked against its effect line;
progress and preservation of the sorts it infers, against eval's step."""

import contextlib
from dataclasses import replace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fpl.ast_core import Bind, Call, Define, Effect, Match, Node, Push, Row, Run, Symbol, Wild
from fpl.driver import run
from fpl.errors import FplError, Span
from fpl.eval import State, running, step
from fpl.types import (
    ARROWS,
    Arrow,
    Input,
    Kind,
    Sort,
    Typing,
    UntypedError,
    after,
    elaborate,
    sort,
)

HERE = Span(1, 1)
AT = Span(2, 3)
BUILTINS = ("+", "-", "times", "dup", "swap", "drop")


@pytest.mark.parametrize(
    ("source", "error"),
    [
        ("f : -- y z\n1 | f +\n", "ERROR: 1:1 f leaves 0 values, its effect line 2"),
        ("f : x -- y z\n\tdup dup\n", "ERROR: 1:1 f leaves 3 values, its effect line 2"),
        ("d/\n\tg : x --\n", "ERROR: 2:2 d/g leaves 1 values, its effect line 0"),
        ("f : x -- y\n\t“a” +\n", "ERROR: 2:6 arithmetic on a non-number"),
        ("f : x -- y\n\t→a a a “b” swap +\n", "ERROR: 2:18 arithmetic on a non-number"),
    ],
)
def test_a_body_is_checked_against_its_effect_line(source: str, error: str) -> None:
    """A declared effect is checked against the body it heads, before any line runs."""
    with pytest.raises(FplError) as caught:
        run(source)
    assert str(caught.value) == error


def test_an_effect_is_inferred_from_the_body() -> None:
    """A word's inputs are as general as its body lets them be; arithmetic makes one a number."""
    swapped = Define("s", Effect(("x", "y"), ("y", "x")), (Call("swap", HERE),))
    summed = Define("t", Effect(("x", "y"), ("z",)), (Call("+", HERE),))
    arrows, _ = elaborate((swapped, summed))
    assert arrows["s"] == Arrow((Input(0), Input(1)), (Input(1), Input(0)))
    assert arrows["t"] == Arrow((Kind.NUMBER, Kind.NUMBER), (Kind.NUMBER,))


def test_a_body_with_a_match_keeps_its_declared_arity() -> None:
    """A match body is not inferred: the effect line stands, its outputs of no known sort."""
    source = "f : x -- y\n\tmatch\n\t\t0\t1\n\t\t_\t2\n0 f\n"
    assert run(source) == "1\n"


def test_calling_a_word_meets_its_inputs() -> None:
    """A defined word's inferred inputs are checked where it is called."""
    with pytest.raises(FplError) as caught:
        run("t : x y -- z\n\t+\n“a” | 1 t\n")
    assert str(caught.value) == "ERROR: 3:9 arithmetic on a non-number"


@pytest.mark.parametrize(
    "node",
    [Bind("x", (), AT), Match((Row((Wild(),), ()),), AT), Call("+", AT)],
    ids=["bind", "match", "call"],
)
def test_taking_from_nothing_is_refused(node: Node) -> None:
    """Below the driver, whose lines never bind or match on an empty stack and whose short
    calls are sections: refused at the node."""
    with pytest.raises(FplError) as caught:
        after(Typing((), {}, {}), (node,), ARROWS)
    assert str(caught.value) == "ERROR: 2:3 stack underflow"


def test_a_name_dies_with_its_binder() -> None:
    """Below the driver, whose binders run to the end of their code: a name read after its
    binder's scope is not bound there."""
    code = (Bind("x", (), HERE), Call("x", HERE))
    with pytest.raises(UntypedError):
        after(Typing((Kind.NUMBER,), {}, {}), code, {})


def goals(source: str) -> list[str]:
    """The goals running the source reports, whether or not it then runs."""
    reported: list[str] = []
    with contextlib.suppress(FplError):
        run(source, reported.append)
    return reported


@pytest.mark.parametrize(
    ("source", "goal"),
    [
        ("m : xs -- x\n\tdup drop ?\n", "GOAL 2:11 ? : t0 -- value"),
        ("f : x y -- z\n\t? +\n", "GOAL 2:2 ? : t0 t1 -- number number"),
        ("f : x y -- z\n\t→a ? a +\n", "GOAL 2:5 ? : t0 -- number"),
        ("f : x -- y\n\tmatch\n\t\t0\t1\n\t\t_\t?\n", "GOAL 4:5 ? : -- value"),
        ("“a” ?\n", "GOAL 1:5 ? : text --"),
        ("f : x -- y\n\t→a ?\n", "GOAL 2:5 ? : -- value"),
    ],
)
def test_a_goal_is_reported_with_the_effect_that_fills_it(source: str, goal: str) -> None:
    """[D2.7] ? is a goal the elaborator reports: it takes the stack under it and leaves what
    the code after it takes, or what the effect line promises when nothing follows."""
    assert goals(source) == [goal]


def test_a_goal_before_a_binder_leaves_what_its_scope_takes() -> None:
    """[D2.7] A goal before a binder leaves the values the scope takes, the scope ending at
    the count the effect line promises."""
    source = "f : x -- y\n\t? →a ?\n"
    assert goals(source) == ["GOAL 2:2 ? : t0 -- value", "GOAL 2:7 ? : -- value"]


@pytest.mark.parametrize(
    ("source", "goal"),
    [
        ("1 ?\n", "GOAL 1:3 ? : number --"),
        ("1 2 3 ?\n", "GOAL 1:7 ? : number --"),
        ("1 “a” 2 ?\n", "GOAL 1:9 ? : value --"),
        ("{ a 1 } ?\n", "GOAL 1:9 ? : value --"),
        ("f : x -- y\n\tmatch\n\t\t0\t“a”\n\t\t_\t“b”\n0 f ?\n", "GOAL 5:5 ? : text --"),
        ("f : x -- y\n\tmatch\n\t\t0\t“a”\n\t\t_\t1\n0 f ?\n", "GOAL 5:5 ? : value --"),
    ],
    ids=["number", "strand", "mixed-strand", "dict", "rows-agree", "rows-differ"],
)
def test_a_goal_shows_the_sorts_under_it(source: str, goal: str) -> None:
    """A literal has its sort, a strand its items' when they share one, a match's output the
    sort its rows agree on; any other value is of none."""
    assert goals(source) == [goal]


def test_a_goal_run_is_refused_where_it_stands() -> None:
    """Elaboration goes on past a goal; running one is refused at it (hole goal-placeholder)."""
    with pytest.raises(FplError) as caught:
        run("f : x -- y\n\t?\n1 f\n")
    assert str(caught.value) == "ERROR: 2:2 unfilled goal"


@pytest.mark.parametrize(
    ("source", "output"),
    [
        ("f : x -- y\n\t_\n1 f\n", "1\n"),
        ("1 _ 2 +\n", "3\n"),
        ("f : x y -- z\n\t_ +\n1 | 2 f\n", "3\n"),
        ("f : x -- y\n\tmatch\n\t\t0\t_\n\t\t_\t_\n\t1\n0 f\n", "1\n"),
    ],
)
def test_a_hole_in_a_term_is_inferred_as_nothing(source: str, output: str) -> None:
    """[D2.7] _ asks the elaborator to infer the code in its place: nothing, when the code
    around it already meets what follows (hole infer-hole)."""
    assert run(source) == output


def test_a_hole_that_is_not_nothing_is_refused_at_its_span() -> None:
    """[D2.7] A _ that nothing fills is refused at it, with the effect it would need."""
    with pytest.raises(FplError) as caught:
        run("f : x -- y z\n\t_\n")
    assert str(caught.value) == "ERROR: 2:2 cannot infer _ : t0 -- value value"


def test_match_rows_leaving_different_counts_keep_the_effect_line() -> None:
    """Rows are typed alike; rows that disagree on their count leave the match untyped, its
    word's effect line trusted (hole effect-line-trusted)."""
    assert run("f : x -- y\n\tmatch\n\t\t0\t1\n\t\t_\t1 dup\n0 f\n") == "1\n"


def test_an_input_a_row_does_arithmetic_on_is_a_number_for_its_word() -> None:
    """A sort a row finds for a value under the match or a name around it holds for the whole
    word, whichever row runs: its callers meet it (hole typed-fragment)."""
    with pytest.raises(FplError) as caught:
        run("f : x y -- z\n\t→a\n\tmatch\n\t\t_\ta 1 +\n0 | “a” f\n")
    assert str(caught.value) == "ERROR: 5:9 arithmetic on a non-number"


def test_rows_agree_on_the_sort_a_later_row_finds() -> None:
    """A row that leaves an input and a row that finds it a number agree that it is one."""
    rows = (Row((Wild(),), ()), Row((Wild(),), (Push(1), Call("+", HERE))))
    arrows, _ = elaborate((Define("f", Effect(("x", "y"), ("z",)), (Match(rows, HERE),)),))
    assert arrows["f"] == Arrow((Kind.NUMBER, Input(1)), (Kind.NUMBER,))


def test_a_match_row_is_typed() -> None:
    """A row's body is typed with its pattern names standing for values of no known sort."""
    with pytest.raises(FplError) as caught:
        run("f : x -- y\n\tmatch\n\t\t( pair a b )\ta “s” +\n")
    assert str(caught.value) == "ERROR: 3:22 arithmetic on a non-number"


@st.composite
def code(draw: st.DrawFn, typing: Typing, arrows: dict[str, Arrow], depth: int) -> tuple[Node, ...]:
    """Nodes that type from `typing`: each drawn, kept only if elaboration accepts it and it
    leaves no value of no tracked sort (as rows that disagree on a sort do, hole typed-fragment);
    a binder takes the top and holds the rest, a match takes the top and runs one of its rows."""
    nodes: list[Node] = []
    defined = (name for name in arrows if name.startswith("w") and "/" not in name)
    words = (*BUILTINS, *defined, *typing.env)
    for _ in range(draw(st.integers(0, 6))):
        if typing.stack and depth and draw(st.booleans()):
            name = f"x{depth}"
            inner = Typing(typing.stack[:-1], {**typing.env, name: typing.stack[-1]}, typing.known)
            return (*nodes, Bind(name, draw(code(inner, arrows, depth - 1)), HERE))
        node = draw(
            st.one_of(
                st.integers(-9, 9).map(Push),
                st.sampled_from(["a", "b"]).map(Push),
                st.sampled_from([Symbol("s")]).map(Push),
                st.sampled_from(words).map(lambda name: Call(name, HERE)),
                *([matches(typing, arrows, depth - 1)] if typing.stack and depth else []),
            )
        )
        with contextlib.suppress(FplError, UntypedError):
            ended = after(typing, (node,), arrows)
            if Kind.VALUE not in ended.stack:
                typing = ended
                nodes.append(node)
    return tuple(nodes)


@st.composite
def matches(draw: st.DrawFn, typing: Typing, arrows: dict[str, Arrow], depth: int) -> Match:
    """A match taking the top with _, each row's body drawn to type on the values under it, so
    that a row can find the sorts of the inputs and names around the match."""
    under = replace(typing, stack=typing.stack[:-1])
    bodies = draw(st.lists(code(under, arrows, depth), min_size=1, max_size=2))
    return Match(tuple(Row((Wild(),), body) for body in bodies), HERE)


@st.composite
def programs(draw: st.DrawFn) -> tuple[tuple[Define, ...], Run]:
    """Words each calling only those before it, then a line calling them."""
    defines: list[Define] = []
    for index in range(draw(st.integers(0, 3))):
        ins = draw(st.integers(0, 2))
        start = Typing(tuple(map(Input, range(ins))), {}, {})
        body = draw(code(start, elaborate(tuple(defines))[0], 2))
        outs = len(after(start, body, elaborate(tuple(defines))[0]).stack)
        effect = Effect(tuple(f"i{n}" for n in range(ins)), tuple(f"o{n}" for n in range(outs)))
        defines.append(Define(f"w{index}", effect, body))
    line = draw(code(Typing((), {}, {}), elaborate(tuple(defines))[0], 2))
    return tuple(defines), Run(line)


def states(defines: tuple[Define, ...], line: Run) -> tuple[dict[str, Arrow], State]:
    """The words' arrows and the state the line starts in."""
    arrows, _ = elaborate((*defines, line))
    return arrows, State((), line.code, {d.name: d.code for d in defines})


def typed(state: State, arrows: dict[str, Arrow]) -> tuple[object, ...]:
    """The sorts the state's code leaves on its stack."""
    sorts: tuple[Sort, ...] = tuple(map(sort, state.stack))
    return after(Typing(sorts, {}, {}), state.code, arrows).stack


@pytest.mark.obligation("progress: a well-typed term is a value or takes a step")
@given(programs())
def test_a_well_typed_program_runs_to_a_value(program: tuple[tuple[Define, ...], Run]) -> None:
    """What elaboration accepts never goes wrong: each state with code left steps."""
    arrows, state = states(*program)
    while running(state):
        state = step(state)
    assert typed(state, arrows) == tuple(map(sort, state.stack))


@pytest.mark.obligation("preservation: a step keeps the type")
@given(programs())
def test_a_step_keeps_the_sorts_a_state_leaves(program: tuple[tuple[Define, ...], Run]) -> None:
    """The sorts a state's code leaves are those of the state one step on."""
    arrows, state = states(*program)
    expected = typed(state, arrows)
    while running(state):
        state = step(state)
        assert typed(state, arrows) == expected
