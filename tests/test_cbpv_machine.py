"""The machine: progress, agreement with the literal CK transcription, fuel and replay on
generated programs; fixed tests for the outcomes and events generated programs rarely show."""

import itertools
from collections.abc import Callable, Iterator
from dataclasses import fields, is_dataclass, replace
from typing import Any

import pytest
from cbpv_ck import ck_run
from cbpv_strategies import (
    BINARY,
    BODY,
    HANDLE,
    INT,
    KEY,
    LOG,
    ONE,
    PANICS,
    PURE,
    SIGMA_TEST,
    TIMES,
    programs,
)
from hypothesis import given
from hypothesis import strategies as st

from fpl.cbpv.check import TypeError_, check_config, fits
from fpl.cbpv.machine import (
    End,
    Event,
    Failed,
    LabelEvent,
    OpEvent,
    OutOfFuel,
    Panicked,
    ReplayDiverged,
    Returned,
    Run_,
    Stuck,
    Unsaturated,
    as_term,
    readback,
    replay,
    run,
    states,
)
from fpl.cbpv.syntax import (
    Absurd,
    App,
    Arrow,
    Comp,
    Const,
    CType,
    Dyn,
    Effects,
    F,
    Fail,
    Force,
    Label,
    Lam,
    Op,
    Position,
    Prim,
    Program,
    Return,
    Thunk,
    To,
    U,
    Var,
)

type View = tuple[tuple[Any, ...], tuple[tuple[Any, ...], ...], int]


def counter() -> Callable[[str, Any, Any], Const]:
    """The test handler: `emit` answers how many operations it has answered, this one included."""
    calls = itertools.count(1)
    return lambda _op, _cap, _arg: Const(next(calls), INT)


def view(r: Run_) -> View:
    """A run as the CK oracle writes it: closures read back to thunks."""
    return _end(r.end), tuple(_event(e) for e in r.trace), r.steps


def _end(end: End) -> tuple[Any, ...]:
    match end:
        case Returned():
            return "returned", readback(end.value)
        case Unsaturated():
            return "unsaturated", readback(end.closure)
        case Failed():
            return "failed", readback(end.payload)
        case Panicked():
            return "panicked", end.payload, end.at
        case _:
            raise AssertionError(end)


def _event(e: Event) -> tuple[Any, ...]:
    if isinstance(e, LabelEvent):
        return "label", e.label
    return "op", e.op, readback(e.cap), readback(e.arg), readback(e.result)


def prims(x: object) -> Iterator[Prim]:
    """Every constant in `x`, a program or a node (only a program holds tuples of nodes)."""
    if isinstance(x, Prim):
        yield x
    elif isinstance(x, Program):
        for part in (*(value for _, value in x.defs), *x.runs):
            yield from prims(part)
    elif is_dataclass(x) and not isinstance(x, type):
        for f in fields(x):
            yield from prims(getattr(x, f.name))


def singles(program: Program) -> Iterator[Program]:
    """Each run of `program` on its own, over the same definitions."""
    return (Program(program.defs, (m,)) for m in program.runs)


@pytest.mark.obligation("progress: a checked run never gets stuck and panics only in a constant")
@given(programs(SIGMA_TEST), st.none() | st.integers(0, 40))
def test_progress(program: Program, fuel: int | None) -> None:
    """[law: progress] For every program `programs(Σ_test)` draws (with `Dyn`) and every fuel
    bound, the machine ends in `Returned`, `Unsaturated`, `Failed`, `OutOfFuel`, or `Panicked`
    with the panic raised by a constant's own domain check, never `Stuck`, and never raises."""
    sites = {p.at for p in prims(program)}
    for r in run(program, SIGMA_TEST, fuel=fuel, handler=counter()):
        assert isinstance(r.end, Returned | Unsaturated | Failed | OutOfFuel | Panicked), r.end
        if isinstance(r.end, Panicked):
            assert r.end.at in sites
            assert r.end.payload in PANICS


@given(programs(SIGMA_TEST))
def test_cek_is_ck(program: Program) -> None:
    """[law: cek-is-ck] On every program `programs(Σ_test)` draws, the environment machine and
    the literal CK transcription (`tests/cbpv_ck.py`) reach the same outcome (up to readback of
    closures to terms), the same trace and the same step count."""
    machine = run(program, SIGMA_TEST, handler=counter())
    assert [view(r) for r in machine] == ck_run(program, SIGMA_TEST, counter())


@given(programs(SIGMA_TEST), st.data())
def test_fuel_monotone(program: Program, data: st.DataObject) -> None:
    """[law: fuel-monotone] For every program `programs(Σ_test)` draws: if its run ends in
    anything but `OutOfFuel` with fuel n, it ends the same, with the same trace and steps, with
    any fuel ≥ n and with none; with less fuel than its steps it ends `OutOfFuel`."""
    for single in singles(program):
        (free,) = run(single, SIGMA_TEST, handler=counter())
        more = data.draw(st.integers(free.steps, free.steps + 3))
        assert run(single, SIGMA_TEST, fuel=more, handler=counter()) == (free,)
        less = data.draw(st.integers(0, free.steps))
        (short,) = run(single, SIGMA_TEST, fuel=less, handler=counter())
        ran_out = (short.end, short.steps) == (OutOfFuel(), less)
        assert short == free if less == free.steps else ran_out


@pytest.mark.obligation("preservation: a step keeps the type of a Dyn-free program")
@given(programs(SIGMA_TEST, dyn=False))
def test_preservation(program: Program) -> None:
    """[law: preservation] For every program `programs(Σ_test, dyn=False)` draws, every state the
    machine passes through reads back (`as_term`) to a configuration `check_config` types at
    the run's type and effect, and a `Returned` value has the run's value type."""
    typed: dict[int, tuple[CType, Effects]] = {}
    for i, state in states(program, SIGMA_TEST, handler=counter()):
        judged = check_config(*as_term(state), SIGMA_TEST)
        assert not isinstance(judged, TypeError_), (judged, as_term(state))
        want = typed.setdefault(i, judged)
        assert fits(judged[0], want[0]) is None
        assert judged[1] <= want[1]
    for i, r in enumerate(run(program, SIGMA_TEST, handler=counter())):
        if isinstance(r.end, Returned):
            returned = check_config(Return(readback(r.end.value)), (), SIGMA_TEST)
            assert not isinstance(returned, TypeError_)
            assert fits(returned[0], typed[i][0]) is None


def _altered(log: tuple[Event, ...], i: int) -> tuple[Event, ...]:
    event = log[i]
    assert isinstance(event, OpEvent)
    return (*log[:i], replace(event, result=Const(-1, INT)), *log[i + 1 :])


def _replayed(program: Program, log: tuple[Event, ...]) -> tuple[Run_, ...] | ReplayDiverged:
    try:
        return run(program, SIGMA_TEST, handler=replay(log))
    except ReplayDiverged as diverged:
        return diverged


@given(programs(SIGMA_TEST), st.data())
def test_replay_deterministic(program: Program, data: st.DataObject) -> None:
    """[law: replay-deterministic] For every program `programs(Σ_test)` draws, replaying its
    run's own trace reproduces its outcome, trace and steps; a trace with one result altered
    raises `ReplayDiverged` at that event or changes the outcome."""
    first = run(program, SIGMA_TEST, handler=counter())
    log = tuple(e for r in first for e in r.trace)
    assert run(program, SIGMA_TEST, handler=replay(log)) == first
    ops = [i for i, e in enumerate(log) if isinstance(e, OpEvent)]
    if ops:
        i = data.draw(st.sampled_from(ops))
        altered = _altered(log, i)
        again = _replayed(program, altered)
        if isinstance(again, ReplayDiverged):
            assert again.index > ops.index(i)
        else:
            assert tuple(e for r in again for e in r.trace)[: i + 1] == altered[: i + 1]
            assert again != first


def only(m: Comp) -> Run_:
    (r,) = run(Program((), (m,)), SIGMA_TEST, handler=counter())
    return r


def test_unsaturated() -> None:
    lam = Lam("x", INT, 1, Return(Var("x")))
    r = only(lam)
    assert isinstance(r.end, Unsaturated)
    closure = r.end.closure
    assert (closure.comp, closure.env, closure.origin, r.steps) == (lam, None, None, 0)


@pytest.mark.parametrize(
    ("m", "reason"),
    [
        (Force(ONE), "force of a non-thunk"),
        (Absurd(ONE, F(INT)), "absurd"),
        (Return(Var("nowhere")), "unbound nowhere"),
        (Prim("add", BINARY, PURE, None), "a constant on the empty stack"),
    ],
)
def test_stuck(m: Comp, reason: str) -> None:
    """A state no rule applies to ends the run `Stuck`, without a step; no checked closed run
    reaches one (absurd: no closed value has type 0, hole absurd-rule)."""
    r = only(m)
    assert isinstance(r.end, Stuck)
    assert (r.end.reason, r.steps) == (reason, 0)


def test_div_by_zero_panics_at_its_site() -> None:
    at = Position(1, 5)
    r = only(App(Const(0, INT), App(ONE, Prim("div", BINARY, PURE, at))))
    assert isinstance(r.end, Panicked)
    assert (r.end.payload, r.end.at, r.steps) == ("division by zero", at, 3)


def test_a_constant_takes_its_arguments_top_first() -> None:
    r = only(App(Const(2, INT), App(Const(7, INT), Prim("sub", BINARY, PURE, None))))
    assert (r.end, r.steps) == (Returned(Const(5, INT)), 3)


def test_times_k_panics_without_a_count() -> None:
    at = Position(2, 3)
    times = Prim("times_k", Arrow(Dyn(), Arrow(U(BODY, PURE), F(INT))), PURE, at)
    body = Thunk(Label(KEY, Lam("n", INT, 1, Return(Var("n")))))
    r = only(App(body, App(Const(HANDLE, Dyn()), times)))
    assert (r.end, r.steps) == (Panicked("times_k takes a count", at), 3)


def test_fail_at_the_root() -> None:
    r = only(To(Fail(ONE), "x", 1, Return(Var("x"))))
    assert isinstance(r.end, Failed)
    assert (r.end.payload, r.steps) == (ONE, 2)


def test_labels_in_a_loop_body_reach_the_trace_in_order() -> None:
    log = Const(HANDLE, LOG)
    body = Thunk(Label(KEY, Lam("n", INT, 1, Op("emit", log, Var("n")))))
    r = only(App(body, App(Const(2, INT), TIMES)))
    assert isinstance(r.end, Returned)
    assert (r.end.value, r.steps) == (Const(2, INT), 13)
    assert [e.label for e in r.trace if isinstance(e, LabelEvent)] == [KEY, KEY]
    assert [(e.op, e.cap, e.arg, e.result) for e in r.trace if isinstance(e, OpEvent)] == [
        ("emit", log, Const(0, INT), Const(1, INT)),
        ("emit", log, Const(1, INT), Const(2, INT)),
    ]
    assert [type(e) for e in r.trace] == [LabelEvent, OpEvent, LabelEvent, OpEvent]


def test_replay_answers_from_the_log() -> None:
    program = Program((), (Op("emit", Const(HANDLE, LOG), ONE),))
    (first,) = run(program, SIGMA_TEST, handler=counter())
    assert run(program, SIGMA_TEST, handler=replay(first.trace)) == (first,)


def test_replay_diverges_past_the_log() -> None:
    op = Op("emit", Const(HANDLE, LOG), ONE)
    with pytest.raises(ReplayDiverged) as caught:
        run(Program((), (op,)), SIGMA_TEST, handler=replay(()))
    diverged = caught.value
    assert (diverged.index, diverged.expected, diverged.got) == (0, None, ("emit", op.cap, ONE))
