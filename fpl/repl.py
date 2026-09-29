"""`python -m fpl.repl`: one input entered at a session's head or evaluated as of an event, a
rewind, the log listed, or the program at an event shown. Without --session the log is empty
and held in memory, so one input runs as its file does. An append is checked against --head
and made durable under the session's lock before anything is printed. Exit 0 ok, 1 the input
failed, 2 argv not taken or a refusal, with nothing written."""

import os
import re
import sys
from argparse import ArgumentParser
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import NoReturn, TextIO, override

from fpl.errors import FplError
from fpl.log import ASCII, U64, Event, Log, RefusedError, Who, keyed, load, locked, resolve, write
from fpl.multihash import Multihash
from fpl.parse import parse
from fpl.print import render
from fpl.session import FUEL_DEFAULT, Context, enter, evaluator, program, rewind

USAGE = (
    "usage: python -m fpl.repl [--session FILE] [--fuel N] [--canonical] [--at EVENT]"
    " [--head EVENT] (-e SOURCE | --rewind EVENT | --log | --show)"
)
ACTIONS = ("source", "rewind", "log", "show")
NUMERAL = re.compile(r"0|[1-9][0-9]*")
EMPTY = Log((), {}, 0)


class UsageError(Exception):
    """argv the command line does not take."""


class _Parser(ArgumentParser):
    """An ArgumentParser that raises where it would print and exit."""

    @override
    def error(self, message: str) -> NoReturn:
        raise UsageError(message)


def _fuel(text: str) -> int:
    """A step budget: a decimal numeral below 2^64, as the log records it."""
    if not NUMERAL.fullmatch(text) or int(text) >= U64:
        raise ValueError(text)
    return int(text)


@dataclass(frozen=True)
class _Call:
    """argv taken: the options, and the one action with its value ("" for a flag)."""

    session: Path | None
    fuel: int
    canonical: bool
    at: str | None
    head: str | None
    action: str
    value: str


def _call(argv: list[str]) -> _Call:
    """argv as a call. Refused (UsageError): anything argparse refuses, no action or two, and
    --at beside --head, --rewind or --log, which name no state to evaluate at."""
    parser = _Parser(add_help=False, allow_abbrev=False)
    parser.add_argument("--session", type=Path)
    parser.add_argument("--fuel", type=_fuel, default=FUEL_DEFAULT)
    parser.add_argument("--canonical", action="store_true")
    parser.add_argument("--at")
    parser.add_argument("--head")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("-e", dest="source")
    action.add_argument("--rewind")
    action.add_argument("--log", action="store_const", const="")
    action.add_argument("--show", action="store_const", const="")
    args = vars(parser.parse_args(argv))
    name = next(name for name in ACTIONS if args[name] is not None)
    if args["at"] is not None and (args["head"] is not None or name in ("rewind", "log")):
        raise UsageError("--at goes with -e or --show")
    fields = ("session", "fuel", "canonical", "at", "head")
    return _Call(**{field: args[field] for field in fields}, action=name, value=args[name])


def provenance(env: Mapping[str, str]) -> tuple[Who, str, str]:
    """Who enters an input, under which model and session: an agent when $FPL_MODEL or
    $FPL_SESSION_ID is set, else an operator. Refused (RefusedError): either not printable
    ASCII of at most 256 characters."""
    names = ("FPL_MODEL", "FPL_SESSION_ID")
    for name in names:
        if not ASCII.fullmatch(env.get(name, "")):
            raise RefusedError(f"${name} is not printable ASCII of at most 256 characters")
    who: Who = "agent" if any(name in env for name in names) else "operator"
    return who, env.get("FPL_MODEL", ""), env.get("FPL_SESSION_ID", "")


@dataclass(frozen=True)
class _Said:
    """What a call prints, and its exit status."""

    out: str
    notes: tuple[str, ...]
    code: int


@dataclass(frozen=True)
class _Change:
    """An event to append, the bodies it names, and what the call prints once it is."""

    event: Event
    bodies: Mapping[Multihash, bytes]
    said: _Said


def _canonical(text: str) -> str:
    """The input as the printer writes it, or nothing when it does not parse alone."""
    try:
        return render(parse(text))
    except FplError:
        return ""


def _entered(call: _Call, log: Log, context: Context, at: Event | None) -> _Change:
    """The input after the program at `at`. Refused: text that is not UTF-8, which argv
    holds as lone surrogates."""
    try:
        call.value.encode()
    except UnicodeEncodeError:
        raise RefusedError("the input is not UTF-8") from None
    outcome = enter(log, call.value, context, at)
    shown = _canonical(call.value) if call.canonical else ""
    code = 0 if outcome.event.status == "ok" else 1
    return _Change(outcome.event, outcome.bodies, _Said(shown + outcome.out, outcome.notes, code))


def _rewound(call: _Call, log: Log, context: Context, _at: Event | None) -> _Change:
    """A rewind of the head to the event named."""
    return _Change(rewind(log, resolve(log, call.value), context), {}, _Said("", (), 0))


def _seq(seqs: Mapping[Multihash, str], ids: tuple[Multihash, ...], none: str) -> str:
    """The seq of the first event named, or `none`."""
    return seqs[ids[0]] if ids else none


def _listed(log: Log, _at: Event | None) -> _Said:
    """A line an event: seq, kind, status, the seq of its dep or 0, of its link or -, id."""
    seqs = {event.ident: str(event.seq) for event in log.events}
    rows = (
        f"{e.seq} {e.kind} {e.status} {_seq(seqs, e.deps, '0')} {_seq(seqs, e.links, '-')}"
        f" ${e.ident.spelled()}\n"
        for e in log.events
    )
    return _Said("".join(rows), (), 0)


def _shown(log: Log, at: Event | None) -> _Said:
    """The program at `at`: its accepted inputs, joined."""
    return _Said("".join(part.text for part in program(log, at)), (), 0)


READERS: dict[str, Callable[[Log, Event | None], _Said]] = {"log": _listed, "show": _shown}
WRITERS: dict[str, Callable[[_Call, Log, Context, Event | None], _Change]] = {
    "source": _entered,
    "rewind": _rewound,
}


def _changed(call: _Call, log: Log, env: Mapping[str, str], at: Event | None) -> _Change:
    """The event the call would append at the head. Refused: a --head that is not it."""
    if call.head is not None and resolve(log, call.head) is not log.head:
        raise RefusedError(f"head moved: the head is {len(log.events)}")
    context = Context(evaluator(), *provenance(env), call.fuel)
    return WRITERS[call.action](call, log, context, at)


def _read(call: _Call, log: Log, env: Mapping[str, str]) -> _Said:
    """A call that appends nothing: a reader, or an input evaluated as of --at, or at the
    head of a log held in memory."""
    at = log.head if call.at is None else resolve(log, call.at)
    if call.action in READERS:
        return READERS[call.action](log, at)
    return _changed(call, log, env, at).said


def _said(call: _Call, env: Mapping[str, str]) -> _Said:
    """The call carried out. An append loads, checks and writes under the lock, and names
    the new head last."""
    if call.session is None:
        return _read(call, EMPTY, env)
    key = keyed(env)
    if call.action in READERS or call.at is not None:
        return _read(call, load(call.session, key), env)
    with locked(call.session):
        log = load(call.session, key)
        change = _changed(call, log, env, log.head)
        write(call.session, key, log, change.event, change.bodies)
    head = f"HEAD {change.event.seq} ${change.event.ident.spelled()}"
    return replace(change.said, notes=(*change.said.notes, head))


def main(
    argv: list[str],
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    env: Mapping[str, str] = os.environ,
) -> int:
    """Carry out argv; the output, or one ERROR line, to stdout; goals, the caret under an
    error, inputs changed and the new head to stderr, all after any append is durable."""
    try:
        said = _said(_call(argv), env)
    except UsageError:
        stderr.write(USAGE + "\n")
        return 2
    except RefusedError as error:
        stdout.write(f"ERROR: {error}\n")
        return 2
    stdout.write(said.out)
    stderr.write("".join(note + "\n" for note in said.notes))
    return said.code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
