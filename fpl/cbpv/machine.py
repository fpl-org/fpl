"""The CK machine for the IR, run as an environment machine with the statement's steps.

`run(program, sig, fuel=..., handler=...)` runs each of the program's runs on an empty stack,
in an environment of its definitions, and returns one `Run_` per run: how it ended, the events
it emitted (each operation with its result, each label), and the steps it took. A state is
`⟨M, E, K⟩`: a computation in focus, a persistent environment (a cons list) from names to
runtime values (constants, pairs, sums, closures), and a stack of frames (a cons list, so a
push is O(1)). One transition is one rule of the statement's CK machine (design section 5), so
the step count is the statement's; the loop is iterative, never recursive.

Steps: a rule that applies is one step, `fail` and a constant's panic included (their rules
end the run); a terminal state (`return V` or `λx. M` on the empty stack) takes none, and
neither does a state no rule applies to (`Stuck`). A terminal state is recognised before fuel
is consulted, so with `fuel=n` a run of at most n steps ends as it does with `fuel=None`, and
a longer one ends `OutOfFuel` after n.

Extensions of the statement, each a hole in HOLES.md: an iterating constant keeps its loop as
a `Loop` frame (iteration-constants); `fail` ends the run, since no term installs a supervisor
frame (fail-frames); `absurd` has no rule and ends `Stuck` (absurd-rule). A run never raises on
a program whose definitions are closed: an unchecked run ends `Stuck`, and only `handler` may
raise (a `replay` handler raises `ReplayDiverged`).
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Generator, Hashable, Iterator
from dataclasses import dataclass, fields, is_dataclass, replace
from typing import Any

from fpl.cbpv.sig import Done, FirstOrder, Iterating, Panic, Signature, Step
from fpl.cbpv.syntax import (
    Absurd,
    App,
    Both,
    Case,
    Comp,
    Const,
    Fail,
    First,
    Force,
    Inl,
    Inr,
    Label,
    LabelKey,
    Lam,
    Op,
    Pair,
    Position,
    Prim,
    Program,
    Rec,
    Return,
    Second,
    SplitPair,
    Thunk,
    To,
    Unit,
    Value,
    Var,
    VType,
)

# Runtime values.


@dataclass(frozen=True, slots=True)
class Closure:
    """A thunk at run time: its body, the environment it closes over, its source quotation."""

    comp: Comp
    env: Env
    origin: int | None


@dataclass(frozen=True, slots=True)
class VPair:
    """`(V, W)` at run time."""

    left: Val
    right: Val


@dataclass(frozen=True, slots=True)
class VInl:
    """`inl V` at run time, with its right summand for readback."""

    value: Val
    right: VType


@dataclass(frozen=True, slots=True)
class VInr:
    """`inr V` at run time, with its left summand for readback."""

    value: Val
    left: VType


type Val = Const | Unit | VPair | VInl | VInr | Closure
type Env = tuple[str, Val, Env] | None

# Frames and states.


@dataclass(frozen=True, slots=True)
class Arg:
    """`V :: K`: an argument for the λ or constant above."""

    value: Val


@dataclass(frozen=True, slots=True)
class Then:
    """`(to x. N) :: K`, with the environment `N` runs in."""

    name: str
    body: Comp
    env: Env


@dataclass(frozen=True, slots=True)
class Fst:
    """`fst :: K`."""


@dataclass(frozen=True, slots=True)
class Snd:
    """`snd :: K`."""


@dataclass(frozen=True, slots=True)
class Loop:
    """`loop(p, s) :: K`: the iterating constant `p` resumes from `s` with its body's result."""

    prim: Prim
    state: Any


type Frame = Arg | Then | Fst | Snd | Loop
type Stack = tuple[Frame, Stack] | None


@dataclass(frozen=True, slots=True)
class State:
    """`⟨M, E, K⟩`: the focus, its environment, the stack."""

    focus: Comp
    env: Env
    stack: Stack


# How a run ends, and what it emits.


@dataclass(frozen=True, slots=True)
class Returned:
    """`return V` on the empty stack."""

    value: Val


@dataclass(frozen=True, slots=True)
class Unsaturated:
    """`λx. M` on the empty stack: the statement's unsaturated word."""

    closure: Closure


@dataclass(frozen=True, slots=True)
class Failed:
    """`fail W` reached the root."""

    payload: Val


@dataclass(frozen=True, slots=True)
class Panicked:
    """A constant refused its arguments; `at` is its call site."""

    payload: Hashable
    at: Position | None


@dataclass(frozen=True, slots=True)
class OutOfFuel:
    """The fuel ran out before the run ended."""


@dataclass(frozen=True, slots=True)
class Stuck:
    """No rule applies: only an unchecked program gets here."""

    reason: str


type End = Returned | Unsaturated | Failed | Panicked | OutOfFuel | Stuck


@dataclass(frozen=True, slots=True)
class OpEvent:
    """`op V W` answered `result`."""

    op: str
    cap: Val
    arg: Val
    result: Val


@dataclass(frozen=True, slots=True)
class LabelEvent:
    """`label l. M` was entered."""

    label: LabelKey


type Event = OpEvent | LabelEvent
type Handler = Callable[[str, Val, Val], Val]


@dataclass(frozen=True, slots=True)
class Run_:  # noqa: N801 -- the design's name; `run` is the function
    """How a run ended, its events in order, and its steps."""

    end: End
    trace: tuple[Event, ...]
    steps: int


class ReplayDiverged(Exception):  # noqa: N818 -- the design's name
    """A replayed run asked for an operation the log does not hold next: `index` counts the
    operations, `expected` is the logged one (`None` past the log's end), `got` the asked."""

    def __init__(self, index: int, expected: OpEvent | None, got: tuple[str, Val, Val]) -> None:
        super().__init__(f"operation {index}: logged {expected!r}, asked {got!r}")
        self.index = index
        self.expected = expected
        self.got = got


def replay(trace: tuple[Event, ...]) -> Handler:
    """A handler answering each operation with the result `trace` logged for it, in order."""
    logged = [e for e in trace if isinstance(e, OpEvent)]
    calls = itertools.count()

    def handler(op: str, cap: Val, arg: Val) -> Val:
        index = next(calls)
        expected = logged[index] if index < len(logged) else None
        if expected is None or (expected.op, expected.cap, expected.arg) != (op, cap, arg):
            raise ReplayDiverged(index, expected, (op, cap, arg))
        return expected.result

    return handler


# Running.


def run(
    program: Program, sig: Signature, *, fuel: int | None = None, handler: Handler
) -> tuple[Run_, ...]:
    """Each run of `program`, on its own stack and with its own `fuel`."""
    return tuple(_finish(_drive(start, _Run(sig, handler, []), fuel)) for start in _starts(program))


def _starts(program: Program) -> Iterator[State]:
    env: Env = None
    for name, value in program.defs:
        env = (name, _value(value, env), env)
    return (State(m, env, None) for m in program.runs)


@dataclass(slots=True)
class _Run:
    sig: Signature
    handler: Handler
    trace: list[Event]

    def end(self, end: End, steps: int) -> Run_:
        return Run_(end, tuple(self.trace), steps)


class _StuckError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _finish(driven: Generator[State, None, Run_]) -> Run_:
    while True:
        try:
            next(driven)
        except StopIteration as stop:
            ended: Run_ = stop.value
            return ended


def _drive(start: State, r: _Run, fuel: int | None) -> Generator[State, None, Run_]:
    """Yield each state from `start` on; return how the run ended."""
    state, steps = start, 0
    while True:
        yield state
        try:
            end = _final(state) or _out_of_fuel(steps, fuel)
            if end is not None:
                return r.end(end, steps)
            after = _RULES[type(state.focus)](state.focus, state, r)
        except _StuckError as stuck:
            return r.end(Stuck(stuck.reason), steps)
        steps += 1
        if not isinstance(after, State):
            return r.end(after, steps)
        state = after


def _final(s: State) -> End | None:
    if s.stack is not None:
        return None
    if isinstance(s.focus, Return):
        return Returned(_value(s.focus.value, s.env))
    if isinstance(s.focus, Lam):
        return Unsaturated(Closure(s.focus, s.env, None))
    return None


def _out_of_fuel(steps: int, fuel: int | None) -> OutOfFuel | None:
    return OutOfFuel() if fuel is not None and steps >= fuel else None


def _expect[T](x: object, kind: type[T], reason: str) -> T:
    if not isinstance(x, kind):
        raise _StuckError(reason)
    return x


def _top(stack: Stack, what: str) -> tuple[Frame, Stack]:
    if stack is None:
        raise _StuckError(f"{what} on the empty stack")
    return stack


# Values.


def _value(v: Value, env: Env) -> Val:
    return _VALUES[type(v)](v, env)


def _find(env: Env, name: str) -> Val | None:
    while env is not None:
        bound, value, env = env
        if bound == name:
            return value
    return None


def _lookup(v: Var, env: Env) -> Val:
    found = _find(env, v.name)
    if found is None:
        raise _StuckError(f"unbound {v.name}")
    return found


_VALUES: dict[type, Callable[[Any, Env], Val]] = {
    Var: _lookup,
    Const: lambda v, _env: v,
    Unit: lambda v, _env: v,
    Pair: lambda v, env: VPair(_value(v.left, env), _value(v.right, env)),
    Inl: lambda v, env: VInl(_value(v.value, env), v.right),
    Inr: lambda v, env: VInr(_value(v.value, env), v.left),
    Thunk: lambda v, env: Closure(v.body, env, v.origin),
}

# The rules, one per focus class.

type Next = State | End
BODY = " body"  # binds the thunk a loop runs, in an environment of its own
RESULT = " result"  # binds an operation's result, likewise


def _rule_app(m: App, s: State, _r: _Run) -> Next:
    return State(m.fun, s.env, (Arg(_value(m.arg, s.env)), s.stack))


def _rule_lam(m: Lam, s: State, _r: _Run) -> Next:
    frame, rest = _top(s.stack, "λ")
    arg = _expect(frame, Arg, "λ without an argument")
    return State(m.body, (m.name, arg.value, s.env), rest)


def _rule_to(m: To, s: State, _r: _Run) -> Next:
    return State(m.bound, s.env, (Then(m.name, m.body, s.env), s.stack))


def _rule_return(m: Return, s: State, r: _Run) -> Next:
    value = _value(m.value, s.env)
    frame, rest = _top(s.stack, "return")
    if isinstance(frame, Then):
        return State(frame.body, (frame.name, value, frame.env), rest)
    loop = _expect(frame, Loop, "return to neither `to` nor a loop")
    return _iterate(loop.prim, _iterating(loop.prim, r).resume(loop.state, value), rest)


def _rule_force(m: Force, s: State, _r: _Run) -> Next:
    closure = _expect(_value(m.value, s.env), Closure, "force of a non-thunk")
    return State(closure.comp, closure.env, s.stack)


def _rule_split(m: SplitPair, s: State, _r: _Run) -> Next:
    pair = _expect(_value(m.value, s.env), VPair, "pm of a non-pair")
    return State(m.body, (m.right, pair.right, (m.left, pair.left, s.env)), s.stack)


def _rule_case(m: Case, s: State, _r: _Run) -> Next:
    value = _value(m.value, s.env)
    if isinstance(value, VInl):
        return State(m.left, (m.left_name, value.value, s.env), s.stack)
    right = _expect(value, VInr, "pm of a non-sum")
    return State(m.right, (m.right_name, right.value, s.env), s.stack)


def _rule_absurd(_m: Absurd, _s: State, _r: _Run) -> Next:
    raise _StuckError("absurd")


def _rule_both(m: Both, s: State, _r: _Run) -> Next:
    frame, rest = _top(s.stack, "⟨M, N⟩")
    if isinstance(frame, Fst):
        return State(m.left, s.env, rest)
    _expect(frame, Snd, "⟨M, N⟩ without a projection")
    return State(m.right, s.env, rest)


def _rule_first(m: First, s: State, _r: _Run) -> Next:
    return State(m.comp, s.env, (Fst(), s.stack))


def _rule_second(m: Second, s: State, _r: _Run) -> Next:
    return State(m.comp, s.env, (Snd(), s.stack))


def _rule_rec(m: Rec, s: State, _r: _Run) -> Next:
    return State(m.body, (m.name, Closure(m, s.env, None), s.env), s.stack)


def _rule_op(m: Op, s: State, r: _Run) -> Next:
    cap, arg = _value(m.cap, s.env), _value(m.arg, s.env)
    result = r.handler(m.op, cap, arg)
    r.trace.append(OpEvent(m.op, cap, arg, result))
    return State(Return(Var(RESULT)), (RESULT, result, None), s.stack)


def _rule_fail(m: Fail, s: State, _r: _Run) -> Next:
    return Failed(_value(m.payload, s.env))


def _rule_label(m: Label, s: State, r: _Run) -> Next:
    r.trace.append(LabelEvent(m.label))
    return State(m.body, s.env, s.stack)


def _rule_prim(m: Prim, s: State, r: _Run) -> Next:
    constant = r.sig.constants.get(m.name)
    if isinstance(constant, FirstOrder):
        args, rest = _pop(s.stack, constant.arity)
        result = constant.apply(tuple(a.value if isinstance(a, Const) else a for a in args), m.at)
        if isinstance(result, Panic):
            return Panicked(result.payload, m.at)
        return State(Return(result), None, rest)
    loop = _iterating(m, r)
    args, rest = _pop(s.stack, loop.arity)
    return _iterate(m, loop.start(args, m.at), rest)


def _iterating(p: Prim, r: _Run) -> Iterating:
    return _expect(r.sig.constants.get(p.name), Iterating, f"no constant {p.name}")


def _pop(stack: Stack, n: int) -> tuple[tuple[Val, ...], Stack]:
    args: list[Val] = []
    for _ in range(n):
        frame, stack = _top(stack, "a constant")
        args.append(_expect(frame, Arg, "a constant without its arguments").value)
    return tuple(args), stack


def _iterate(p: Prim, step: Step | Panic, rest: Stack) -> Next:
    """`start` or `resume` answered: run the body above a loop frame, return, or panic."""
    if isinstance(step, Panic):
        return Panicked(step.payload, p.at)
    if isinstance(step, Done):
        return State(Return(step.value), None, rest)
    stack: Stack = (Loop(p, step.state), rest)
    for arg in reversed(step.args):
        stack = (Arg(arg), stack)
    return State(Force(Var(BODY)), (BODY, step.thunk, None), stack)


_RULES: dict[type, Callable[[Any, State, _Run], Next]] = {
    App: _rule_app,
    Lam: _rule_lam,
    To: _rule_to,
    Return: _rule_return,
    Force: _rule_force,
    SplitPair: _rule_split,
    Case: _rule_case,
    Absurd: _rule_absurd,
    Both: _rule_both,
    First: _rule_first,
    Second: _rule_second,
    Rec: _rule_rec,
    Op: _rule_op,
    Fail: _rule_fail,
    Label: _rule_label,
    Prim: _rule_prim,
}

# Readback.


def readback(v: Val) -> Value:
    """The syntax value `v` stands for: a closure reads back as its body with its environment
    substituted (the innermost binding of a name wins; a binder in the body shadows it)."""
    return _READBACK[type(v)](v)


_READBACK: dict[type, Callable[[Any], Value]] = {
    Const: lambda v: v,
    Unit: lambda v: v,
    VPair: lambda v: Pair(readback(v.left), readback(v.right)),
    VInl: lambda v: Inl(readback(v.value), v.right),
    VInr: lambda v: Inr(readback(v.value), v.left),
    Closure: lambda v: Thunk(_close(v.comp, v.env, frozenset()), v.origin),
}

# Which fields each binder's names scope over.
_BINDS: dict[type, dict[str, tuple[str, ...]]] = {
    Lam: {"body": ("name",)},
    To: {"body": ("name",)},
    Rec: {"body": ("name",)},
    SplitPair: {"body": ("left", "right")},
    Case: {"left": ("left_name",), "right": ("right_name",)},
}


def _close(x: Any, env: Env, bound: frozenset[str]) -> Any:
    """`x` with each free name that `env` binds, and `bound` does not, read back from `env`."""
    if isinstance(x, Var):
        found = None if x.name in bound else _find(env, x.name)
        return x if found is None else readback(found)
    if not is_dataclass(x) or isinstance(x, type):
        return x
    binds = _BINDS.get(type(x), {})
    return replace(
        x,
        **{
            f.name: _close(
                getattr(x, f.name), env, bound | {getattr(x, n) for n in binds.get(f.name, ())}
            )
            for f in fields(x)
        },
    )
