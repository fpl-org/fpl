"""Events named by the hash of their header bytes, kept as FON records that read back only as
they were written."""

import dataclasses
import os
import re
import stat
import tempfile
import threading
from collections.abc import Sequence
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from test_multihash import digest

from fpl import fon
from fpl.log import (
    KINDS,
    SCHEMA,
    STATUSES,
    WHO,
    Event,
    Log,
    RefusedError,
    keyed,
    load,
    locked,
    parsed,
    record,
    write,
)
from fpl.multihash import BLAKE2B_256, Multihash, content, hashed, spelling

KEY = bytes(range(32))
u64 = st.integers(0, 2**64 - 1)
ident = digest.map(lambda d: Multihash(BLAKE2B_256, d))
idents = st.lists(ident, max_size=3).map(tuple)
blob = st.binary(max_size=64).map(content)
ascii_text = st.text(st.characters(min_codepoint=0x20, max_codepoint=0x7E), max_size=256)
event = st.builds(
    Event,
    schema=st.just(SCHEMA),
    evaluator=ident,
    kind=st.sampled_from(KINDS),
    seq=u64,
    deps=idents,
    links=idents,
    body=blob,
    out=blob,
    status=st.sampled_from(STATUSES),
    who=st.sampled_from(WHO),
    model=ascii_text,
    session=ascii_text,
    fuel=u64,
)
BASE = Event(
    SCHEMA,
    hashed(b"fpl"),
    "input",
    2,
    (hashed(b"1"),),
    (),
    content(b"1 2 +\n"),
    content(b"3\n"),
    "ok",
    "agent",
    "Claude Opus 5.5",
    "s",
    1_000_000,
)
LINE = record(BASE, KEY)[:-1]


def split(data: bytes) -> list[bytes]:
    """data cut at its eight-byte big-endian length prefixes, nothing left over."""
    parts: list[bytes] = []
    at = 0
    while at < len(data):
        assert len(data) - at >= 8
        end = at + 8 + int.from_bytes(data[at : at + 8], "big")
        assert end <= len(data)
        parts.append(data[at + 8 : end])
        at = end
    return parts


def number(raw: bytes) -> int:
    """Eight big-endian bytes as a number."""
    assert len(raw) == 8
    return int.from_bytes(raw, "big")


def multihash(raw: bytes) -> Multihash:
    """A raw multihash, read through its hex alias."""
    return spelling(raw.hex(), inline=True)


def decoded(preimage: bytes) -> tuple[object, ...]:
    """The thirteen fields a preimage holds, read back as the values they encode."""
    fields = split(preimage)
    assert len(fields) == 13
    schema, evaluator, kind, seq, deps, links, body, out, status, who, model, session, fuel = fields
    return (
        number(schema),
        multihash(evaluator),
        kind.decode(),
        number(seq),
        tuple(map(multihash, split(deps))),
        tuple(map(multihash, split(links))),
        multihash(body),
        multihash(out),
        status.decode(),
        who.decode(),
        model.decode("ascii"),
        session.decode("ascii"),
        number(fuel),
    )


@given(event, event)
def test_header_bytes(a: Event, b: Event) -> None:
    """[law: header-bytes] the id preimage decodes by its length prefixes into the thirteen
    fields; distinct events give distinct preimages; records round-trip under a fixed key."""
    fields = tuple(getattr(a, field.name) for field in dataclasses.fields(a))
    assert decoded(a.header()) == fields
    assert (a.header() == b.header()) == (a == b) == (a.ident == b.ident)
    assert a.ident == hashed(a.header())
    line = record(a, KEY)
    assert line.endswith(b"\n")
    assert b"\n" not in line[:-1]
    assert parsed(line[:-1], KEY) == a
    assert fon.write(fon.read(line[:-1].decode())) == line[:-1].decode()


def test_record_spelling() -> None:
    """A record is one FON dict, its keys in header order, then id and mac."""
    assert re.fullmatch(
        r"\{ schema 1 evaluator &45600:\d+ kind input seq 2 deps ⟨ \$45600:\d+ ⟩ links ⟨⟩"
        r" body &0:6:\d+ out &0:2:\d+ status ok who agent model “Claude Opus 5.5” session “s”"
        r" fuel 1000000 id \$45600:\d+ mac &0:32:\d+ \}",
        LINE.decode(),
    )


@pytest.mark.parametrize(
    ("old", "new", "reason"),
    [
        ("{ schema 1 ", "{ ", "fields differ from schema evaluator"),
        (LINE.decode(), "⟨⟩", "fields differ from schema evaluator"),
        (LINE.decode(), "{", "1:1 { never closed"),
        ("schema 1", "schema 2", "schema 2 is unknown"),
        ("seq 2", "seq 2.5", "seq is not a number below 2^64"),
        ("seq 2", "seq -1", "seq is not a number below 2^64"),
        ("seq 2", f"seq {2**64}", "seq is not a number below 2^64"),
        ("seq 2", "seq x", "seq is not a number below 2^64"),
        ("evaluator &", "evaluator $", "evaluator is not a hash"),
        ("kind input", "kind bogus", "kind is not one of input rewind"),
        ("status ok", "status “ok”", "status is not one of ok error"),
        ("deps ⟨ $", "deps ⟨ &", "an item of deps is not an identity"),
        ("links ⟨⟩", "links _", "links is not a list"),
        ("model “Claude", "model “Clé", "model is not printable ASCII of at most 256 characters"),
        ("session “s”", "session s", "session is not printable ASCII of at most 256"),
        ("id $", "id &", "id is not an identity"),
        ("who agent", "who operator", "id does not recompute"),
        ("seq 2", "seq 2.0", "not canonical"),
        ("fuel 1000000", "fuel  1000000", "not canonical"),
    ],
)
def test_record_refused(old: str, new: str, reason: str) -> None:
    """A record the writer would not have written, byte for byte, is refused."""
    assert old in LINE.decode()
    with pytest.raises(RefusedError, match=r"^" + reason.replace("^", r"\^")):
        parsed(LINE.decode().replace(old, new, 1).encode(), KEY)


def test_record_keyed() -> None:
    """Bytes that are not UTF-8, or a mac made under another key, are refused."""
    with pytest.raises(RefusedError, match=r"^not UTF-8$"):
        parsed(b"\xff", KEY)
    with pytest.raises(RefusedError, match="mac does not verify"):
        parsed(LINE, bytes(32))


type Step = tuple[bool, int, bytes, bytes]
type Link = tuple[Event, dict[Multihash, bytes]]
step = st.tuples(st.booleans(), st.integers(0, 4), st.binary(max_size=64), st.binary(max_size=64))


def chained(steps: Sequence[Step]) -> list[Link]:
    """Events that follow one another: an input extends the origin or an earlier event; a
    rewind, once there is a head, abandons it for the origin or an event before it."""
    links: list[Link] = []
    for seq, (back, pick, body, out) in enumerate(steps, 1):
        idents = [event.ident for event, _ in links]
        rewind = back and bool(idents)
        earlier = idents[:-1] if rewind else idents
        deps = (earlier[pick - 1],) if 0 < pick <= len(earlier) else ()
        event = dataclasses.replace(
            BASE,
            kind="rewind" if rewind else "input",
            seq=seq,
            deps=deps,
            links=(idents[-1],) if rewind else (),
            body=content(body),
            out=content(out),
        )
        links.append((event, {content(body): body, content(out): out}))
    return links


def appended(path: Path, links: Sequence[Link], log: Log) -> Log:
    """log after each link is written to path in turn."""
    for event, bodies in links:
        log = write(path, KEY, log, event, bodies)
    return log


@given(st.lists(step, min_size=1, max_size=5), st.data())
def test_log_load(steps: list[Step], data: st.DataObject) -> None:
    """[law: log-load] ids recompute on load and are distinct; any byte flip in a complete
    record is refused; a torn tail reads as the prefix and the next append replaces it; a wrong
    key is refused; the old file is a byte prefix of the new one."""
    links = chained(steps)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory, "s.log")
        log = load(path, KEY)
        for link in links:
            old = path.read_bytes() if path.exists() else b""
            log = appended(path, [link], log)
            assert path.read_bytes().startswith(old)
            assert load(path, KEY) == log
        events = [event for event, _ in links]
        assert log.events == tuple(events)
        assert log.head == events[-1]
        assert [event.ident for event in log.events] == [hashed(e.header()) for e in events]
        assert len({event.ident for event in log.events}) == len(events)
        whole = path.read_bytes()
        assert log.size == len(whole)
        with pytest.raises(RefusedError, match=f"^{re.escape(str(path))}:1 mac does not verify"):
            load(path, bytes(32))
        at = data.draw(st.integers(0, len(whole) - 2))
        flip = data.draw(st.integers(1, 255))
        path.write_bytes(whole[:at] + bytes([whole[at] ^ flip]) + whole[at + 1 :])
        with pytest.raises(RefusedError):
            load(path, KEY)
        cut = data.draw(st.integers(0, len(record(events[-1], KEY)) - 1))
        path.write_bytes(whole[: len(whole) - len(record(events[-1], KEY)) + cut])
        prefix = load(path, KEY)
        assert prefix.events == log.events[:-1]
        assert appended(path, links[-1:], prefix) == log
        assert path.read_bytes() == whole


def tampered(path: Path, events: Sequence[Event]) -> None:
    """path holding events as records, however they follow one another."""
    path.write_bytes(b"".join(record(event, KEY) for event in events))


FIRST = dataclasses.replace(BASE, seq=1, deps=())
LONG = b"1 2 +\n" * 8


@pytest.mark.parametrize(
    ("events", "reason"),
    [
        ([BASE], "1 seq 2 is not 1"),
        ([dataclasses.replace(FIRST, deps=(hashed(b"1"),))], "1 names no earlier event"),
        (
            [FIRST, dataclasses.replace(BASE, links=(FIRST.ident,), deps=())],
            "2 input has deps 0 and links 1",
        ),
        (
            [FIRST, dataclasses.replace(BASE, kind="rewind", deps=())],
            "2 rewind has deps 0 and links 0",
        ),
        (
            [
                FIRST,
                dataclasses.replace(BASE, kind="rewind", deps=(FIRST.ident,), links=(FIRST.ident,)),
            ],
            "2 deps and links overlap",
        ),
        (
            [FIRST, dataclasses.replace(BASE, deps=(FIRST.ident, FIRST.ident))],
            "2 input has deps 2 and links 0",
        ),
        (
            [dataclasses.replace(FIRST, body=hashed(LONG))],
            f"1 body {hashed(LONG).spelled()} is missing",
        ),
    ],
)
def test_load_refused(tmp_path: Path, events: list[Event], reason: str) -> None:
    """A record that does not follow the records before it is refused at load, and never
    written."""
    path = tmp_path / "s.log"
    tampered(path, events)
    with pytest.raises(RefusedError, match=f"^{re.escape(str(path))}:{reason}"):
        load(path, KEY)
    *before, last = events
    tampered(path, before)
    with pytest.raises(RefusedError, match=reason.split(" ", 1)[1]):
        write(path, KEY, load(path, KEY), last, {})
    assert path.read_bytes() == b"".join(record(event, KEY) for event in before)


@pytest.mark.parametrize(
    ("event", "reason"),
    [
        (dataclasses.replace(FIRST, schema=2), "schema 2 is unknown"),
        (dataclasses.replace(FIRST, model="m" * 257), "model is not printable ASCII"),
        (dataclasses.replace(FIRST, model="a\x01b"), "model is not printable ASCII"),
        (
            dataclasses.replace(FIRST, fuel=2**64),
            "a number is not below 2\\^64 or a text is not ASCII$",
        ),
        (
            dataclasses.replace(FIRST, session="é"),
            "a number is not below 2\\^64 or a text is not ASCII$",
        ),
    ],
)
def test_write_refused(tmp_path: Path, event: Event, reason: str) -> None:
    """An event load would refuse is refused before anything is written, its bodies included."""
    path = tmp_path / "s.log"
    with pytest.raises(RefusedError, match=f"^{reason}"):
        write(path, KEY, Log((), {}, 0), event, {hashed(LONG): LONG})
    assert list(tmp_path.iterdir()) == []


def test_bodies_hash_to_their_names(tmp_path: Path) -> None:
    """A body longer than 32 bytes is kept beside the log under its name; a file that does not
    hash to its name, or a hashed name for bytes held inline, is refused."""
    path = tmp_path / "s.log"
    event = dataclasses.replace(FIRST, body=hashed(LONG))
    log = write(path, KEY, load(path, KEY), event, {hashed(LONG): LONG, BASE.out: b"3\n"})
    store = tmp_path / "s.log.bodies"
    kept = store / hashed(LONG).spelled()
    assert kept.read_bytes() == LONG
    assert load(path, KEY).bodies == log.bodies == {hashed(LONG): LONG, BASE.out: b"3\n"}
    assert os.listdir(store) == [hashed(LONG).spelled()]
    modes = [stat.S_IMODE(each.stat().st_mode) for each in (store, kept, path)]
    assert modes == [0o700, 0o600, 0o600]
    again = dataclasses.replace(BASE, deps=(event.ident,), body=hashed(LONG))
    assert write(path, KEY, log, again, {}).bodies == log.bodies
    kept.write_bytes(LONG + b"\n")
    with pytest.raises(RefusedError, match=r":1 body 45600:[0-9]+ does not hash to its name"):
        load(path, KEY)
    short = dataclasses.replace(FIRST, body=hashed(b"3\n"))
    with pytest.raises(RefusedError, match="does not hash to its name"):
        write(tmp_path / "t.log", KEY, Log((), {}, 0), short, {hashed(b"3\n"): b"3\n"})


def test_framing(tmp_path: Path) -> None:
    """No file is the empty log; an empty line is a record, and refused."""
    path = tmp_path / "s.log"
    assert load(path, KEY) == Log((), {}, 0)
    assert load(path, KEY).head is None
    path.write_bytes(b"\n")
    with pytest.raises(RefusedError, match=":1 fields differ"):
        load(path, KEY)


def test_short_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A write the system cuts short raises, leaving a torn tail the next load drops."""
    path = tmp_path / "s.log"
    real = os.write

    def short(fd: int, data: bytes) -> int:
        return real(fd, data[:-1])

    monkeypatch.setattr(os, "write", short)
    with pytest.raises(OSError, match="short write"):
        write(path, KEY, load(path, KEY), FIRST, {})
    monkeypatch.undo()
    assert load(path, KEY) == Log((), {}, 0)


def test_appends_under_a_lock(tmp_path: Path) -> None:
    """Eight writers of three appends each leave twenty-four events, numbered in order."""
    path = tmp_path / "s.log"

    def appends() -> None:
        for _ in range(3):
            with locked(path):
                log = load(path, KEY)
                deps = (log.head.ident,) if log.head else ()
                event = dataclasses.replace(FIRST, seq=len(log.events) + 1, deps=deps)
                write(path, KEY, log, event, {})

    writers = [threading.Thread(target=appends) for _ in range(8)]
    for writer in writers:
        writer.start()
    for writer in writers:
        writer.join()
    assert [event.seq for event in load(path, KEY).events] == list(range(1, 25))


def test_key(tmp_path: Path) -> None:
    """The key is made once, 32 bytes only its owner reads, found through FPL_LOG_KEY, then
    XDG_CONFIG_HOME, then HOME."""
    home = {"HOME": str(tmp_path)}
    key = keyed(home)
    made = tmp_path / ".config" / "fpl" / "log.key"
    assert len(key) == 32
    assert stat.S_IMODE(made.stat().st_mode) == 0o600
    assert stat.S_IMODE(made.parent.stat().st_mode) == 0o700
    assert keyed(home) == key
    assert os.listdir(tmp_path / ".config") == ["fpl"]
    assert keyed({"XDG_CONFIG_HOME": str(tmp_path / ".config")}) == key
    assert keyed({"FPL_LOG_KEY": str(made), "HOME": "/nonexistent"}) == key
    with pytest.raises(RefusedError, match=r"^no key file: \$FPL_LOG_KEY, \$XDG_CONFIG_HOME and"):
        keyed({})
    made.chmod(0o640)
    with pytest.raises(RefusedError, match=r"log\.key is open to others"):
        keyed(home)
    made.chmod(0o600)
    made.write_bytes(bytes(31))
    with pytest.raises(RefusedError, match=r"log\.key holds 31 bytes, not 32"):
        keyed(home)
