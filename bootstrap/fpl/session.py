"""A session over a log: the state at an event is every accepted input its deps lead back
through, run again as one file; entering an input prints only what its own lines leave, and
names, once, each earlier input whose output the input moved from what the state before it
printed. Pure but for `evaluator`, which reads the package's sources once."""

from bisect import bisect_right
from collections.abc import Mapping
from dataclasses import dataclass, replace
from functools import cache, cached_property
from pathlib import Path

from fpl.driver import Lines, checked, printed, stacks
from fpl.errors import FplError, Span
from fpl.log import SCHEMA, Event, Log, RefusedError, Status, Who, prefixed
from fpl.multihash import Multihash, content, hashed
from fpl.types import Goal, reported

FUEL_DEFAULT = 1_000_000
MARGIN = "an input starts at the left margin"


@dataclass(frozen=True)
class Context:
    """What every event of a call records beside its input: the evaluator, who entered it,
    under which model and session, and the step budget of each run line (HOLES.md:
    fuel-scope)."""

    evaluator: Multihash
    who: Who
    model: str
    session: str
    fuel: int


@dataclass(frozen=True)
class Part:
    """An accepted input of a program, and its text."""

    event: Event
    text: str


@dataclass(frozen=True)
class Outcome:
    """An entered input: its event, the bytes of the body and output it names, the output for
    stdout and the notes for stderr (goals met, the caret under an error, inputs changed)."""

    event: Event
    bodies: Mapping[Multihash, bytes]
    out: str
    notes: tuple[str, ...]


@cache
def evaluator() -> Multihash:
    """The hash of the package's sources, each name and its bytes length-prefixed, in name
    order: every edit to the evaluator names a new one."""
    here = Path(__file__).parent
    sources = sorted([*here.glob("*.py"), *here.glob("*.lark")])
    return hashed(b"".join(prefixed(f.name.encode()) + prefixed(f.read_bytes()) for f in sources))


def program(log: Log, at: Event | None) -> tuple[Part, ...]:
    """The accepted inputs of the state at `at`, oldest first: the ok inputs among `at` and
    the events its deps lead back through to the origin, which None is. An error or a rewind
    adds nothing, so an error's program is its parent's and a rewind's its target's."""
    events = {each.ident: each for each in log.events}
    parts: list[Part] = []
    while at is not None:
        if at.kind == "input" and at.status == "ok":
            parts.append(Part(at, log.bodies[at.body].decode()))
        at = events[at.deps[0]] if at.deps else None
    return tuple(reversed(parts))


def _next(log: Log, context: Context, at: Event | None) -> Event:
    """An ok input of nothing after the last event, extending the state at `at`."""
    empty = content(b"")
    return Event(
        schema=SCHEMA,
        evaluator=context.evaluator,
        kind="input",
        seq=len(log.events) + 1,
        deps=(at.ident,) if at else (),
        links=(),
        body=empty,
        out=empty,
        status="ok",
        who=context.who,
        model=context.model,
        session=context.session,
        fuel=context.fuel,
    )


@dataclass(frozen=True)
class _Entry:
    """An input after the program at an event, and where each part and the input start in the
    source they join into."""

    log: Log
    at: Event | None
    context: Context
    parts: tuple[Part, ...]
    text: str

    @cached_property
    def source(self) -> str:
        """The program at the input's state: its parts, joined."""
        return "".join(part.text for part in self.parts)

    @cached_property
    def starts(self) -> tuple[int, ...]:
        """The line each part starts at, then the line the input starts at."""
        starts = [1]
        for part in self.parts:
            starts.append(starts[-1] + part.text.count("\n"))
        return tuple(starts)

    def owner(self, line: int) -> int:
        """The index of the part a line of the joined source lies in; the input's is last."""
        return bisect_right(self.starts, line) - 1

    def local(self, span: Span) -> Span:
        """A span of the joined source as its owner counts it."""
        return Span(span.line - self.starts[self.owner(span.line)] + 1, span.col)

    def margin(self) -> None:
        """Refuse an input after the first whose first non-blank line is indented: joined, it
        would become the block of the input before it. A first input stays its own file."""
        lines = self.text.split("\n")
        first = next((line for line in lines if line.strip()), "")
        if self.parts and first[:1].isspace():
            raise FplError(Span(self.starts[-1] + lines.index(first), 1), MARGIN)

    def noted(self, goals: tuple[Goal, ...]) -> tuple[str, ...]:
        """The goals met in the input, at their place in it."""
        mine = (g for g in goals if self.owner(g.span.line) == len(self.parts))
        return tuple(reported(replace(g, span=self.local(g.span))) for g in mine)

    def logged(self, status: Status, out: str, notes: tuple[str, ...]) -> Outcome:
        """The input as an event with its output."""
        body, shown = self.text.encode(), out.encode()
        event = replace(
            _next(self.log, self.context, self.at),
            body=content(body),
            out=content(shown),
            status=status,
        )
        return Outcome(event, {event.body: body, event.out: shown}, out, notes)


def _failed(entry: _Entry, error: FplError, notes: tuple[str, ...]) -> Outcome:
    """The error as an error event: its line at its place in the input, or `@<seq>` and its
    place in the earlier input it lies in; the caret under it, shown in that input, noted."""
    owner = entry.owner(error.span.line)
    local = FplError(entry.local(error.span), error.message)
    texts = (*(part.text for part in entry.parts), entry.text)
    where = f"@{entry.parts[owner].event.seq} " if owner < len(entry.parts) else ""
    line = f"ERROR: {where}{local.span.line}:{local.span.col} {local.message}"
    caret = local.render(texts[owner]).partition("\n")[2]
    return entry.logged("error", line + "\n", (*notes, caret) if caret else notes)


def _by_part(entry: _Entry, lines: Lines) -> list[Lines]:
    """The lines of a run grouped by the part they lie in, the input's last."""
    groups: list[Lines] = [() for _ in entry.starts]
    for line, stack in lines:
        groups[entry.owner(line)] += ((line, stack),)
    return groups


def _changed(entry: _Entry, left: Lines, before: Lines, notes: tuple[str, ...]) -> Outcome:
    """The input's output, the notes given, then each earlier input whose lines print other
    than they did in `before`, the run of the state the input extends: a move is named at the
    input that makes it, and not again."""
    now, was = _by_part(entry, left), _by_part(entry, before)
    moved = (
        part.event
        for part, new, old in zip(entry.parts, now, was, strict=False)
        if printed(new) != printed(old)
    )
    changed = tuple(f"CHANGED {e.seq} ${e.ident.spelled()}" for e in moved)
    return entry.logged("ok", printed(now[-1]), notes + changed)


def enter(log: Log, text: str, context: Context, at: Event | None) -> Outcome:
    """The outcome of `text` after the program at `at` (None, the origin), not yet appended.
    The input gains a final newline if it lacks one. Joined after the program's parts, it is
    run as one file; its goals are noted even when the run then fails, and any FplError, from
    the margin rule on, becomes an error event whose state is its parent's. The program at `at`
    is run once more, for the lines to compare the new run's with."""
    entry = _Entry(log, at, context, program(log, at), text if text.endswith("\n") else text + "\n")
    notes: tuple[str, ...] = ()
    try:
        entry.margin()
        statements, goals = checked(entry.source + entry.text)
        notes = entry.noted(goals)
        left = stacks(statements, context.fuel)
        before = stacks(checked(entry.source)[0], context.fuel)
    except FplError as error:
        return _failed(entry, error, notes)
    return _changed(entry, left, before, notes)


def rewind(log: Log, target: Event | None, context: Context) -> Event:
    """A rewind of the head to `target` (None, the origin): its state is the target's and it
    links the head it leaves. Refused (RefusedError): an empty log, or the head as target."""
    head = log.head
    if head is None:
        raise RefusedError("nothing to rewind")
    if target == head:
        raise RefusedError("cannot rewind to the head")
    return replace(_next(log, context, target), kind="rewind", links=(head.ident,))
