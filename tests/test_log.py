"""Events named by the hash of their header bytes, kept as FON records that read back only as
they were written."""

import dataclasses
import re

import pytest
from hypothesis import given
from hypothesis import strategies as st
from test_multihash import digest

from fpl import fon
from fpl.log import KINDS, SCHEMA, STATUSES, WHO, Event, RefusedError, parsed, record
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
    with pytest.raises(RefusedError, match=reason.replace("^", r"\^")):
        parsed(LINE.decode().replace(old, new, 1).encode(), KEY)


def test_record_keyed() -> None:
    """Bytes that are not UTF-8, or a mac made under another key, are refused."""
    with pytest.raises(RefusedError, match="not UTF-8"):
        parsed(b"\xff", KEY)
    with pytest.raises(RefusedError, match="mac does not verify"):
        parsed(LINE, bytes(32))
