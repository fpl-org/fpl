"""The session log's events: an input, or a rewind, named by the blake2b-256 of its header
bytes and kept as one canonical FON record per line, with a keyed blake2b of its id beside it
(HOLES.md: log-signing). A record reads back only as the writer would have written it; the
log loads only as a chain of records each following those before it, and grows only by a
durable append under a lock."""

import contextlib
import fcntl
import hashlib
import hmac
import os
import re
import secrets
from collections.abc import Generator, Mapping
from dataclasses import dataclass
from decimal import Decimal
from functools import cached_property
from pathlib import Path
from typing import Literal

from fpl import fon
from fpl.errors import FplError
from fpl.fon import Cell, Dict, Hash, List, Num, Str, Sym, Value
from fpl.multihash import INLINE, Multihash, content, hashed, spelling

type Kind = Literal["input", "rewind"]
type Status = Literal["ok", "error"]
type Who = Literal["agent", "operator"]

SCHEMA = 1
KINDS: tuple[Kind, ...] = ("input", "rewind")
STATUSES: tuple[Status, ...] = ("ok", "error")
WHO: tuple[Who, ...] = ("agent", "operator")
FIELDS = (
    "schema",
    "evaluator",
    "kind",
    "seq",
    "deps",
    "links",
    "body",
    "out",
    "status",
    "who",
    "model",
    "session",
    "fuel",
    "id",
    "mac",
)
KEYS = tuple(Sym(name) for name in FIELDS)
ASCII = re.compile(r"[\x20-\x7e]{0,256}")
U64 = 1 << 64


class RefusedError(Exception):
    """A record or an append refused; nothing was written."""


def u64(n: int) -> bytes:
    """n as eight big-endian bytes."""
    return n.to_bytes(8, "big")


def prefixed(data: bytes) -> bytes:
    """data after its length, as eight big-endian bytes."""
    return u64(len(data)) + data


def _joined(ids: tuple[Multihash, ...]) -> bytes:
    """Raw multihashes, each length-prefixed."""
    return b"".join(prefixed(each.raw()) for each in ids)


@dataclass(frozen=True)
class Event:
    """One step of a session: an input of `body` whose output is `out`, or a rewind. `deps`
    names the event whose state it extends, `links` the head it abandons; `fuel` is the step
    budget each run line had."""

    schema: int
    evaluator: Multihash
    kind: Kind
    seq: int
    deps: tuple[Multihash, ...]
    links: tuple[Multihash, ...]
    body: Multihash
    out: Multihash
    status: Status
    who: Who
    model: str
    session: str
    fuel: int

    def header(self) -> bytes:
        """The id preimage: the thirteen fields in order, each length-prefixed; numbers as
        eight big-endian bytes, multihashes raw, deps and links a length-prefixed run of raw
        multihashes, text ASCII. Numbers of 2^64 or more and text beyond ASCII are refused."""
        fields = (
            u64(self.schema),
            self.evaluator.raw(),
            self.kind.encode(),
            u64(self.seq),
            _joined(self.deps),
            _joined(self.links),
            self.body.raw(),
            self.out.raw(),
            self.status.encode(),
            self.who.encode(),
            self.model.encode("ascii"),
            self.session.encode("ascii"),
            u64(self.fuel),
        )
        return b"".join(prefixed(field) for field in fields)

    @cached_property
    def ident(self) -> Multihash:
        """The event's $: the blake2b-256 of its header, no domain tag, since $ is & applied
        to the log."""
        return hashed(self.header())


def mac(ident: Multihash, key: bytes) -> Multihash:
    """The keyed blake2b-256 of an id, 32 bytes held inline. It lies outside the preimage, so
    a signature can replace it without renaming history."""
    return content(hashlib.blake2b(ident.raw(), digest_size=32, key=key).digest())


def record(event: Event, key: bytes) -> bytes:
    """The event as one canonical FON dict and a newline, UTF-8: its fields in header order,
    then id and mac."""
    values: tuple[Value, ...] = (
        Num(Decimal(event.schema)),
        Hash(event.evaluator),
        Sym(event.kind),
        Num(Decimal(event.seq)),
        List(tuple(map(Cell, event.deps))),
        List(tuple(map(Cell, event.links))),
        Hash(event.body),
        Hash(event.out),
        Sym(event.status),
        Sym(event.who),
        Str(event.model),
        Str(event.session),
        Num(Decimal(event.fuel)),
        Cell(event.ident),
        Hash(mac(event.ident, key)),
    )
    return (fon.write(Dict(tuple(zip(KEYS, values, strict=True)))) + "\n").encode()


def _fields(line: bytes) -> dict[str, Value]:
    """The values of a record's fifteen keys, which must stand in order."""
    try:
        value = fon.read(line.decode())
    except UnicodeDecodeError:
        raise RefusedError("not UTF-8") from None
    except FplError as error:
        raise RefusedError(f"{error.span.line}:{error.span.col} {error.message}") from None
    if not isinstance(value, Dict) or tuple(key for key, _ in value.entries) != KEYS:
        raise RefusedError("fields differ from " + " ".join(FIELDS))
    return {name: item for name, (_, item) in zip(FIELDS, value.entries, strict=True)}


def _number(fields: dict[str, Value], name: str) -> int:
    """A whole number below 2^64."""
    value = fields[name]
    if isinstance(value, Num) and value.value % 1 == 0 and 0 <= value.value < U64:
        return int(value.value)
    raise RefusedError(f"{name} is not a number below 2^64")


def _hash(fields: dict[str, Value], name: str) -> Multihash:
    """A &."""
    value = fields[name]
    if isinstance(value, Hash):
        return value.ref
    raise RefusedError(f"{name} is not a hash")


def _identity(value: Value, what: str) -> Multihash:
    """A $ that names by hash."""
    if isinstance(value, Cell) and isinstance(value.name, Multihash):
        return value.name
    raise RefusedError(f"{what} is not an identity")


def _identities(fields: dict[str, Value], name: str) -> tuple[Multihash, ...]:
    """A list of $ that name by hash."""
    value = fields[name]
    if not isinstance(value, List):
        raise RefusedError(f"{name} is not a list")
    return tuple(_identity(item, f"an item of {name}") for item in value.items)


def _choice[T: str](fields: dict[str, Value], name: str, choices: tuple[T, ...]) -> T:
    """One of a few symbols."""
    for choice in choices:
        if fields[name] == Sym(choice):
            return choice
    raise RefusedError(f"{name} is not one of {' '.join(choices)}")


def _text(fields: dict[str, Value], name: str) -> str:
    """Printable ASCII of at most 256 characters."""
    value = fields[name]
    if isinstance(value, Str) and ASCII.fullmatch(value.text):
        return value.text
    raise RefusedError(f"{name} is not printable ASCII of at most 256 characters")


def _event(fields: dict[str, Value]) -> Event:
    """The event the thirteen header fields spell."""
    return Event(
        schema=_number(fields, "schema"),
        evaluator=_hash(fields, "evaluator"),
        kind=_choice(fields, "kind", KINDS),
        seq=_number(fields, "seq"),
        deps=_identities(fields, "deps"),
        links=_identities(fields, "links"),
        body=_hash(fields, "body"),
        out=_hash(fields, "out"),
        status=_choice(fields, "status", STATUSES),
        who=_choice(fields, "who", WHO),
        model=_text(fields, "model"),
        session=_text(fields, "session"),
        fuel=_number(fields, "fuel"),
    )


def parsed(line: bytes, key: bytes) -> Event:
    """The event a record spells, given without its newline. Refused (RefusedError, the reason
    bare): bytes not UTF-8 or not FON, keys other than the fifteen in order, a value of the
    wrong kind or out of range, a schema other than 1, an id that does not recompute, a mac
    that does not verify under `key`, any spelling `record` would not have written."""
    fields = _fields(line)
    event = _event(fields)
    if event.schema != SCHEMA:
        raise RefusedError(f"schema {event.schema} is unknown")
    if _identity(fields["id"], "id") != event.ident:
        raise RefusedError("id does not recompute")
    if not hmac.compare_digest(_hash(fields, "mac").raw(), mac(event.ident, key).raw()):
        raise RefusedError("mac does not verify")
    if record(event, key) != line + b"\n":
        raise RefusedError("not canonical")
    return event


@dataclass(frozen=True)
class Log:
    """The events of a session file in order, the bytes every body and output they name, and
    the size of the file's complete records; a torn tail lies beyond `size`."""

    events: tuple[Event, ...]
    bodies: Mapping[Multihash, bytes]
    size: int

    @property
    def head(self) -> Event | None:
        """The last event, or None before the first."""
        return self.events[-1] if self.events else None

    def grown(self, event: Event, bodies: Mapping[Multihash, bytes], size: int) -> "Log":
        """The log with one more event, its bodies, and the file's size after its record."""
        return Log((*self.events, event), {**self.bodies, **bodies}, size)


def _follows(idents: set[Multihash], event: Event) -> None:
    """Refuse an event that is not the next of `idents`, names an event not among them, names
    one event both as its state and as the head it abandons, or has more deps or links than
    its kind: an input one dep at most and no link, a rewind one dep at most and one link."""
    if event.seq != len(idents) + 1:
        raise RefusedError(f"seq {event.seq} is not {len(idents) + 1}")
    if not idents.issuperset(event.deps + event.links):
        raise RefusedError("names no earlier event")
    if set(event.deps) & set(event.links):
        raise RefusedError("deps and links overlap")
    links = 1 if event.kind == "rewind" else 0
    if len(event.deps) > 1 or len(event.links) != links:
        raise RefusedError(f"{event.kind} has deps {len(event.deps)} and links {len(event.links)}")


def _store(path: Path) -> Path:
    """The directory beside the log that holds bodies of more than 32 bytes by name."""
    return Path(f"{path}.bodies")


def _stored(path: Path, name: Multihash) -> bytes | None:
    """The bytes a name holds inline, or the file the store keeps under it; None if none."""
    if name.code == INLINE:
        return name.digest
    try:
        return (_store(path) / name.spelled()).read_bytes()
    except FileNotFoundError:
        return None


def _bodies(path: Path, event: Event, given: Mapping[Multihash, bytes]) -> dict[Multihash, bytes]:
    """The event's body and output, from `given` or else the store, each refused unless it is
    exactly the bytes its name promises: one & per byte string, so a hashed name for bytes
    that fit inline is refused too."""
    found: dict[Multihash, bytes] = {}
    for name in (event.body, event.out):
        data = given[name] if name in given else _stored(path, name)
        if data is None:
            raise RefusedError(f"body {name.spelled()} is missing")
        if content(data) != name:
            raise RefusedError(f"body {name.spelled()} does not hash to its name")
        found[name] = data
    return found


def load(path: Path, key: bytes) -> Log:
    """The log a session file holds; no file is the empty log. Records end in a newline, so
    bytes after the last newline are a torn append, dropped. Record n is refused as
    `<path>:<n> <reason>` for anything `parsed` refuses, a seq other than n, a dep or link
    naming no earlier event, deps and links that overlap, arity its kind does not have, or a
    body missing or other than its name; readers take no lock."""
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return Log((), {}, 0)
    complete, newline, _ = data.rpartition(b"\n")
    events: list[Event] = []
    idents: set[Multihash] = set()
    bodies: dict[Multihash, bytes] = {}
    for n, line in enumerate(complete.split(b"\n") if newline else [], 1):
        try:
            event = parsed(line, key)
            _follows(idents, event)
            bodies.update(_bodies(path, event, {}))
        except RefusedError as error:
            raise RefusedError(f"{path}:{n} {error}") from None
        events.append(event)
        idents.add(event.ident)
    return Log(tuple(events), bodies, len(complete) + len(newline))


def _ident(name: str) -> Multihash | None:
    """The id a name spells after an optional $, in decimal or as a hex multihash; None if
    it spells none."""
    try:
        return spelling(name.removeprefix("$"), inline=False)
    except ValueError:
        return None


def resolve(log: Log, name: str) -> Event | None:
    """The event an operator names: 0 the origin, which None is; a seq as written; else an
    id. Refused (RefusedError): a name no event of the log answers to."""
    if name == "0":
        return None
    ident = _ident(name)
    for event in log.events:
        if name == str(event.seq) or event.ident == ident:
            return event
    raise RefusedError(f"no event {name}")


def _written(fd: int, data: bytes) -> None:
    """All of data written to fd at once, or OSError."""
    if os.write(fd, data) != len(data):
        raise OSError(f"short write of {len(data)} bytes")


def _synced(directory: Path) -> None:
    """A directory's entries made durable."""
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _kept(store: Path, name: Multihash, data: bytes) -> None:
    """data durable in the store under its name, whole or not at all. A store made here has its
    own entry synced too, so a record naming a body in it never outlives the store."""
    with contextlib.suppress(FileExistsError):
        store.mkdir(mode=0o700)
        _synced(store.parent)
    temporary = store / f".{name.spelled()}.tmp"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        _written(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, store / name.spelled())
    _synced(store)


def _recorded(event: Event, key: bytes) -> bytes:
    """The event's record. Refused (RefusedError): one `parsed` would not read back, and a
    number of 2^64 or more or a model or session not ASCII, which no record can spell."""
    try:
        line = record(event, key)
    except (OverflowError, UnicodeEncodeError):
        raise RefusedError("a number is not below 2^64 or a text is not ASCII") from None
    parsed(line.removesuffix(b"\n"), key)
    return line


def write(path: Path, key: bytes, log: Log, event: Event, bodies: Mapping[Multihash, bytes]) -> Log:
    """The log after appending event, whose body and output are in `bodies` or already
    stored. The caller holds `locked(path)` and loaded `log` under it. An event `load` would
    refuse after `log` is refused (RefusedError) before anything is written. Bodies are made
    durable first, so a reader never meets a record whose body is missing; then any torn tail
    past `log.size` is cut and the record appended in one write, and file and directory are
    synced before this returns (HOLES.md: log-fsync-barrier)."""
    _follows({each.ident for each in log.events}, event)
    line = _recorded(event, key)
    found = _bodies(path, event, bodies)
    for name, data in found.items():
        if name.code != INLINE and name in bodies:
            _kept(_store(path), name, data)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.ftruncate(fd, log.size)
        _written(fd, line)
        os.fsync(fd)
    finally:
        os.close(fd)
    _synced(path.parent)
    return log.grown(event, found, log.size + len(line))


@contextlib.contextmanager
def locked(path: Path) -> Generator[None]:
    """An exclusive lock on the session at path, held for the block: a blocking flock on
    `<path>.lock` through a descriptor of its own, so threads exclude one another too."""
    fd = os.open(f"{path}.lock", os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _key_file(env: Mapping[str, str]) -> Path:
    """$FPL_LOG_KEY, else $XDG_CONFIG_HOME/fpl/log.key, else $HOME/.config/fpl/log.key.
    Refused (RefusedError): none of the three set."""
    if env.get("FPL_LOG_KEY"):
        return Path(env["FPL_LOG_KEY"])
    if env.get("XDG_CONFIG_HOME"):
        return Path(env["XDG_CONFIG_HOME"], "fpl", "log.key")
    if env.get("HOME"):
        return Path(env["HOME"], ".config", "fpl", "log.key")
    raise RefusedError("no key file: $FPL_LOG_KEY, $XDG_CONFIG_HOME and $HOME are unset")


def _made(directory: Path, mode: int) -> None:
    """directory and its missing ancestors made from the top down, ancestors with the default
    mode and directory with mode, each one's entry synced into its parent before the next is
    made under it. The deepest one found made, before the loop or inside it, has its entry
    synced all the same: a racing maker may not have run that sync yet. Those above it need
    none, as such a maker synced each before it made the next under it."""
    missing: list[Path] = []
    while not directory.exists():
        missing.append(directory)
        directory = directory.parent
    _synced(directory.parent)
    for made in reversed(missing):
        with contextlib.suppress(FileExistsError):
            made.mkdir(mode=mode if made == missing[0] else 0o777)
        _synced(made.parent)


def keyed(env: Mapping[str, str]) -> bytes:
    """The key that macs this operator's records, made on first use as 32 random bytes in a
    file only its owner may read, in a directory only its owner may enter. Each directory made
    on the way, and the deepest one found, has its entry synced into its parent, and the
    file's bytes, once read, and its entry in its directory are synced before the key is used,
    made here or found made by a racing maker whose own sync may not have run, so no record
    outlives the key that macs it.
    The bytes are read before their sync, so none read can have been written after it.
    Refused: a key file others may read or write, or one not 32 bytes long; a reader racing
    the first maker may meet it empty and be refused."""
    path = _key_file(env)
    _made(path.parent, 0o700)
    with contextlib.suppress(FileExistsError):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            _written(fd, secrets.token_bytes(32))
        finally:
            os.close(fd)
    with path.open("rb") as file:
        if os.fstat(file.fileno()).st_mode & 0o077:
            raise RefusedError(f"{path} is open to others")
        key = file.read()
        os.fsync(file.fileno())
    _synced(path.parent)
    if len(key) != 32:
        raise RefusedError(f"{path} holds {len(key)} bytes, not 32")
    return key
