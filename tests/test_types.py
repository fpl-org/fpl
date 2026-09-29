"""Elaboration: each word's effect inferred from its body and checked against its effect line;
progress and preservation of the sorts it infers, against eval's step."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fpl.ast_core import Bind, Call, Define, Effect, Node, Push, Run, Symbol
from fpl.driver import run
from fpl.errors import FplError, Span
from fpl.eval import State, running, step
from fpl.types import Arrow, Input, Kind, Sort, Typing, after, elaborate, sort

HERE = Span(1, 1)
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
    """[D3.4] A declared effect is checked against the body it heads, before any line runs."""
    with pytest.raises(FplError) as caught:
        run(source)
    assert str(caught.value) == error


def test_an_effect_is_inferred_from_the_body() -> None:
    """A word's inputs are as general as its body lets them be; arithmetic makes one a number."""
    swapped = Define("s", Effect(("x", "y"), ("y", "x")), (Call("swap", HERE),))
    summed = Define("t", Effect(("x", "y"), ("z",)), (Call("+", HERE),))
    arrows = elaborate((swapped, summed))
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


def test_a_binder_on_nothing_is_refused() -> None:
    """Below the driver, whose lines never bind on an empty stack: the binder refuses there."""
    with pytest.raises(FplError, match="stack underflow"):
        after(Typing((), {}, {}), (Bind("x", (), HERE),), {})


@st.composite
def code(draw: st.DrawFn, typing: Typing, arrows: dict[str, Arrow], depth: int) -> tuple[Node, ...]:
    """Nodes that type from `typing`: each drawn, kept only if elaboration accepts it; a binder
    takes the top and holds the rest."""
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
            )
        )
        try:
            typing = after(typing, (node,), arrows)
        except FplError:
            continue
        nodes.append(node)
    return tuple(nodes)


@st.composite
def programs(draw: st.DrawFn) -> tuple[tuple[Define, ...], Run]:
    """Words each calling only those before it, then a line calling them."""
    defines: list[Define] = []
    for index in range(draw(st.integers(0, 3))):
        ins = draw(st.integers(0, 2))
        start = Typing(tuple(map(Input, range(ins))), {}, {})
        body = draw(code(start, elaborate(tuple(defines)), 2))
        outs = len(after(start, body, elaborate(tuple(defines))).stack)
        effect = Effect(tuple(f"i{n}" for n in range(ins)), tuple(f"o{n}" for n in range(outs)))
        defines.append(Define(f"w{index}", effect, body))
    line = draw(code(Typing((), {}, {}), elaborate(tuple(defines)), 2))
    return tuple(defines), Run(line)


def states(defines: tuple[Define, ...], line: Run) -> tuple[dict[str, Arrow], State]:
    """The words' arrows and the state the line starts in."""
    arrows = elaborate((*defines, line))
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
