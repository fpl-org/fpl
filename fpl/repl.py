"""`python -m fpl.repl`: one input entered at a session's head or evaluated as of an event, a
rewind, the log listed, or the program at an event shown; with none of these, inputs read one
after another, each as its own -e. Without --session the log is empty and held in memory, so
one input runs as its file does. An append is checked against --head and made durable under
the session's lock before anything is printed. Exit 0 ok, 1 the input failed, 2 argv not taken
or a refusal, with nothing written."""

import importlib
import itertools
import os
import re
import sys
from argparse import ArgumentParser
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import NoReturn, TextIO, override

from fpl.errors import FplError
from fpl.log import ASCII, U64, Event, Log, RefusedError, Who, keyed, load, locked, resolve, write
from fpl.multihash import Multihash
from fpl.parse import parse
from fpl.print import render
from fpl.session import FUEL_DEFAULT, Context, enter, evaluator, program, rewind
from fpl.trivia import head

USAGE = (
    "usage: python -m fpl.repl [--session FILE] [--fuel N] [--canonical] [--at EVENT]"
    " [--head EVENT] [-e SOURCE | --rewind EVENT | --log | --show]"
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
    """argv as a call; with no action, the loop. Refused (UsageError): anything argparse
    refuses, two actions, and --at beside --head, --rewind or --log, which name no state to
    evaluate at."""
    parser = _Parser(add_help=False, allow_abbrev=False)
    parser.add_argument("--session", type=Path)
    parser.add_argument("--fuel", type=_fuel, default=FUEL_DEFAULT)
    parser.add_argument("--canonical", action="store_true")
    parser.add_argument("--at")
    parser.add_argument("--head")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("-e", dest="source")
    action.add_argument("--rewind")
    action.add_argument("--log", action="store_const", const="")
    action.add_argument("--show", action="store_const", const="")
    args = vars(parser.parse_args(argv))
    name = next((name for name in ACTIONS if args[name] is not None), "loop")
    if args["at"] is not None and (args["head"] is not None or name in ("rewind", "log")):
        raise UsageError("--at goes with -e or --show")
    fields = ("session", "fuel", "canonical", "at", "head")
    value = args.get(name) or ""
    return _Call(**{field: args[field] for field in fields}, action=name, value=value)


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


def _reads(call: _Call) -> bool:
    """The call appends nothing: a reader, or an input evaluated as of --at."""
    return call.action in READERS or call.at is not None


def _kept(call: _Call, env: Mapping[str, str], memory: Log) -> tuple[_Said, Log]:
    """The call on a log held in memory; an append grows it and names no head."""
    if _reads(call):
        return _read(call, memory, env), memory
    change = _changed(call, memory, env, memory.head)
    return change.said, memory.grown(change.event, change.bodies, memory.size)


def _said(call: _Call, env: Mapping[str, str], memory: Log) -> tuple[_Said, Log]:
    """The call carried out, and the log as it stands after it. An append loads, checks and
    writes under the lock, and names the new head last."""
    if call.session is None:
        return _kept(call, env, memory)
    key = keyed(env)
    if _reads(call):
        log = load(call.session, key)
        return _read(call, log, env), log
    with locked(call.session):
        log = load(call.session, key)
        change = _changed(call, log, env, log.head)
        log = write(call.session, key, log, change.event, change.bodies)
    head = f"HEAD {change.event.seq} ${change.event.ident.spelled()}"
    return replace(change.said, notes=(*change.said.notes, head)), log


def pending(text: str) -> bool:
    """The input goes on: a pair left open, a definition head or a line with a block last,
    or a trailing / (a directory head)."""
    try:
        last = parse(text).lines[-1]
    except FplError as error:
        return error.message.endswith("never closed")
    return head(last) or bool(last.block) or text.rstrip().endswith("/")


def inputs(read: Callable[[bool], str | None]) -> Iterator[str]:
    """Physical lines, read until None, grouped into inputs: an input ends at a blank line or
    at a line after which it is not pending, and blank lines between inputs are skipped.
    Each input is its lines, each ending in a newline; `read` is told whether one goes on."""
    text = ""
    while (line := read(bool(text))) is not None:
        blank = not line.strip()
        if not blank:
            text += line + "\n"
        if text and (blank or not pending(text)):
            yield text
            text = ""
    if text:
        yield text


def _plain(stdin: TextIO) -> Callable[[bool], str | None]:
    """Lines from a stream that is not a terminal, without prompts."""

    def read(_on: bool) -> str | None:
        line = stdin.readline()
        return line.removesuffix("\n") if line else None

    return read


def _typed(on: bool) -> str | None:
    """A line from the terminal under readline, prompted by whether an input goes on."""
    try:
        return input("...  " if on else "fpl> ")
    except EOFError:
        return None


def _reader(stdin: TextIO) -> Callable[[bool], str | None]:
    """The terminal through readline, where a tab inserts itself (an indent), or the stream."""
    if not stdin.isatty():
        return _plain(stdin)
    readline = importlib.import_module("readline")
    readline.parse_and_bind("tab: self-insert")
    return _typed


def _commanded(call: _Call, text: str) -> _Call:
    """A : command as the call it makes; :log and :rewind name no state to evaluate at.
    Refused: a command not known."""
    match text.split():
        case [":show"]:
            return replace(call, action="show")
        case [":log"]:
            return replace(call, action="log", at=None)
        case [":rewind", event]:
            return replace(call, action="rewind", value=event, at=None)
        case [":canonical"]:
            return replace(call, action="canonical", canonical=not call.canonical)
        case _:
            raise RefusedError("unknown command")


def _told(said: _Said, stdout: TextIO, stderr: TextIO) -> None:
    """The output to stdout, flushed for whoever drives the loop, the notes to stderr."""
    stdout.write(said.out)
    stdout.flush()
    stderr.write("".join(note + "\n" for note in said.notes))


def _seen(call: _Call, log: Log) -> _Call:
    """The call checked against the head of `log`, unless it evaluates as of --at."""
    return call if call.at is not None else replace(call, head=str(len(log.events)))


def _turn(
    call: _Call, text: str, env: Mapping[str, str], log: Log, streams: tuple[TextIO, TextIO]
) -> tuple[_Call, Log]:
    """One input, entered as -e enters it, or one command, carried out and told; the call and
    log the next one starts from. A refusal is told, and the head as it now stands adopted."""
    stdout, stderr = streams
    try:
        this = (
            _commanded(call, text)
            if text.startswith(":")
            else replace(call, action="source", value=text)
        )
        if this.action == "canonical":
            return this, log
        said, log = _said(this, env, log)
    except RefusedError as error:
        _told(_Said(f"ERROR: {error}\n", (), 2), stdout, stderr)
        log = _loaded(call, env, log)
    else:
        _told(said, stdout, stderr)
    return _seen(call, log), log


def _loaded(call: _Call, env: Mapping[str, str], memory: Log) -> Log:
    """The session's log as it stands, or the log held in memory."""
    return memory if call.session is None else load(call.session, keyed(env))


def _looped(
    call: _Call,
    read: Callable[[bool], str | None],
    streams: tuple[TextIO, TextIO],
    env: Mapping[str, str],
) -> int:
    """Inputs and commands until the end or :quit, each checked against the head last seen:
    --head at first, else the head at start. Refused: a log that does not load at start."""
    log = _loaded(call, env, EMPTY)
    if call.head is None:
        call = _seen(call, log)
    for text in itertools.takewhile(lambda t: t.split() != [":quit"], inputs(read)):
        call, log = _turn(call, text, env, log, streams)
    return 0


def main(
    argv: list[str],
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    env: Mapping[str, str] = os.environ,
) -> int:
    """Carry out argv; the output, or one ERROR line, to stdout; goals, the caret under an
    error, inputs changed and the new head to stderr, all after any append is durable."""
    try:
        call = _call(argv)
        if call.action == "loop":
            return _looped(call, _reader(stdin), (stdout, stderr), env)
        said = _said(call, env, EMPTY)[0]
    except UsageError:
        stderr.write(USAGE + "\n")
        return 2
    except RefusedError as error:
        stdout.write(f"ERROR: {error}\n")
        return 2
    _told(said, stdout, stderr)
    return said.code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
