"""The session log's events: an input, or a rewind, named by the blake2b-256 of its header
bytes and kept as one canonical FON record per line, with a keyed blake2b of its id beside it
(HOLES.md: log-signing). A record reads back only as the writer would have written it."""

import hashlib
import hmac
import re
from dataclasses import dataclass
from decimal import Decimal
from functools import cached_property
from typing import Literal

from fpl import fon
from fpl.errors import FplError
from fpl.fon import Cell, Dict, Hash, List, Num, Str, Sym, Value
from fpl.multihash import Multihash, content, hashed

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
