"""Multihashes read back from their decimal spelling and their hex alias, and from nothing else."""

import re

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fpl.multihash import BLAKE2B_256, INLINE, Multihash, content, hashed, spelling

DECIMAL = re.compile(r"(0|[1-9][0-9]*)(:(0|[1-9][0-9]*)){1,2}")

digest = st.tuples(st.integers(0, 32), st.binary(min_size=32, max_size=32)).map(
    lambda zeros_bytes: bytes(zeros_bytes[0]) + zeros_bytes[1][zeros_bytes[0] :]
)
multihash = st.one_of(
    st.binary(max_size=32).map(lambda data: Multihash(INLINE, data)),
    digest.map(lambda d: Multihash(BLAKE2B_256, d)),
)
unknown = st.integers(min_value=1, max_value=1 << 63).filter(lambda code: code != BLAKE2B_256)


def padded(m: Multihash, groups: int, field: int) -> str:
    """m's hex alias with its code (field 0) or length (field 1) varint stretched by redundant
    zero groups."""
    raw = m.raw()
    end = [at for at, byte in enumerate(raw) if byte < 0x80][field] + 1
    varint = raw[: end - 1] + bytes([raw[end - 1] | 0x80]) + b"\x80" * (groups - 1) + b"\x00"
    return (varint + raw[end:]).hex()


stretch = st.tuples(st.integers(1, 3), st.integers(0, 1))
data = st.one_of(st.binary(max_size=80), st.integers(30, 35).map(bytes))


@given(multihash, unknown, digest, stretch, data)
def test_multihash_roundtrip(
    m: Multihash, code: int, d: bytes, stretch: tuple[int, int], data: bytes
) -> None:
    """[law: multihash-roundtrip] spelling(m.spelled()) == m == spelling(m.raw().hex()), leading
    zero bytes included; decimal parts have no leading zeros; unknown codes, the unencoded
    b22020 form and non-minimal varints are refused; content() is inline exactly when at most
    32 bytes."""
    assert spelling(m.spelled(), inline=True) == m == spelling(m.raw().hex(), inline=True)
    assert DECIMAL.fullmatch(m.spelled())
    stranger = Multihash(code, d)
    for text in (stranger.spelled(), stranger.raw().hex(), "b22020" + d.hex()):
        with pytest.raises(ValueError, match=r"^unknown multihash code"):
            spelling(text, inline=True)
    with pytest.raises(ValueError, match=r"^non-minimal varint"):
        spelling(padded(m, *stretch), inline=True)
    with pytest.raises(ValueError, match=r"^inline bytes cannot stand for an identity"):
        spelling(content(data[:32]).raw().hex(), inline=False)
    short = len(data) <= 32
    assert content(data) == (Multihash(INLINE, data) if short else hashed(data))
    assert (content(data).code == INLINE) == short


@pytest.mark.parametrize(
    ("text", "inline", "error"),
    [
        ("45600:01", True, "malformed decimal multihash"),
        ("45600:", True, "malformed decimal multihash"),
        ("0:5", True, "malformed decimal multihash"),
        ("45600:1:2", True, "malformed decimal multihash"),
        ("٣:1", True, "malformed decimal multihash"),
        ("7:1", True, "unknown multihash code 7"),
        ("0:33:0", True, "digest length 33 is wrong for code 0"),
        ("0:99999999999999999999:0", True, "digest length 99999999999999999999 is wrong"),
        ("0:1:256", True, "number too large for 1 bytes"),
        (f"45600:{1 << 256}", True, "number too large for 32 bytes"),
        ("0:0:0", False, "inline bytes cannot stand for an identity"),
        ("abcdef", True, "varint cut short"),
        ("00", True, "varint cut short"),
        ("zz", True, "malformed hex multihash"),
        ("", True, "malformed hex multihash"),
        ("ABCD", True, "malformed hex multihash"),
        ("a0e40221" + "00" * 33, True, "digest length 33 is wrong for code 45600"),
        ("a0e40220" + "00" * 31, True, "digest length differs from 32"),
        ("000100ff", True, "digest length differs from 1"),
    ],
)
def test_a_malformed_multihash_is_refused(text: str, inline: bool, error: str) -> None:
    with pytest.raises(ValueError, match=r"^" + re.escape(error)):
        spelling(text, inline=inline)


def test_a_varint_of_128_takes_two_bytes() -> None:
    """128 is the least number LEB128 spells in two bytes."""
    assert Multihash(128, b"").raw() == bytes([0x80, 0x01, 0x00])


def test_blake2b_is_the_hash_of_record() -> None:
    """The empty input's blake2b-256, as b2sum -l 256 gives it."""
    assert hashed(b"").raw().hex() == (
        "a0e40220" + "0e5751c026e543b2e8ab2eb06099daa1d1e5df47778f7787faab45cdf12fe3a8"
    )
    assert content(b"abc").spelled() == "0:3:6382179"
