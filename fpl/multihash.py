"""Multihashes spelled in decimal: <code>:<n> for a digest, 0:<len>:<n> for bytes held inline,
where <n> is the digest read as a big-endian number; the lower-case hex of the raw multihash
reads as an alias. Codes known: 0 (inline, at most 32 bytes) and 45600 (blake2b-256); every
other code is refused (HOLES.md: log-hash-stand-in)."""

import hashlib
import re
from dataclasses import dataclass

INLINE = 0
BLAKE2B_256 = 45600
LENGTHS: dict[int, range] = {INLINE: range(33), BLAKE2B_256: range(32, 33)}
NUMERAL = re.compile(r"0|[1-9][0-9]*")
HEX = re.compile(r"(?:[0-9a-f]{2})+")


def _leb128(n: int) -> bytes:
    """n as minimal unsigned LEB128."""
    out = bytearray()
    while n >= 0x80:
        out.append(n & 0x7F | 0x80)
        n >>= 7
    out.append(n)
    return bytes(out)


@dataclass(frozen=True)
class Multihash:
    """A self-describing digest: the code names how `digest` was made from the content."""

    code: int
    digest: bytes

    def spelled(self) -> str:
        """The decimal spelling: <code>:<n>, or 0:<len>:<n> inline, since leading zero bytes
        are lost in <n>."""
        n = int.from_bytes(self.digest, "big")
        return f"0:{len(self.digest)}:{n}" if self.code == INLINE else f"{self.code}:{n}"

    def raw(self) -> bytes:
        """varint(code) + varint(length) + digest, the bytes the hex alias spells."""
        return _leb128(self.code) + _leb128(len(self.digest)) + self.digest


def hashed(data: bytes) -> Multihash:
    """The blake2b-256 of data."""
    return Multihash(BLAKE2B_256, hashlib.blake2b(data, digest_size=32).digest())


def content(data: bytes) -> Multihash:
    """The & of data: the bytes themselves up to 32, their hash beyond; one & per byte string."""
    return Multihash(INLINE, data) if len(data) <= 32 else hashed(data)


def _checked(code: int, length: int, inline: bool) -> None:
    """Refuse an unknown code, a digest length the code does not make, or inline bytes where
    only a hash may stand."""
    lengths = LENGTHS.get(code)
    if lengths is None:
        raise ValueError(f"unknown multihash code {code}")
    if length not in lengths:
        raise ValueError(f"digest length {length} is wrong for code {code}")
    if code == INLINE and not inline:
        raise ValueError("inline bytes cannot stand for an identity")


def _numerals(parts: list[str]) -> list[int]:
    """ASCII numerals without leading zeros, as numbers."""
    if not all(NUMERAL.fullmatch(part) for part in parts):
        raise ValueError("malformed decimal multihash")
    return [int(part) for part in parts]


def _decimal(parts: list[str], inline: bool) -> Multihash:
    """<code>:<n> or 0:<len>:<n>."""
    match _numerals(parts):
        case [0, length, n]:
            code = INLINE
        case [code, n] if code != INLINE and code in LENGTHS:
            length = LENGTHS[code].start
        case [code, _] if code != INLINE:
            raise ValueError(f"unknown multihash code {code}")
        case _:
            raise ValueError("malformed decimal multihash")
    _checked(code, length, inline)
    if n.bit_length() > 8 * length:
        raise ValueError(f"number too large for {length} bytes")
    return Multihash(code, n.to_bytes(length, "big"))


def _varint(raw: bytes, at: int) -> tuple[int, int]:
    """The minimal unsigned LEB128 number starting at `at`, and the offset after it."""
    value = 0
    for offset in range(at, len(raw)):
        byte = raw[offset]
        value |= (byte & 0x7F) << 7 * (offset - at)
        if byte < 0x80:
            if byte == 0 and offset > at:
                raise ValueError("non-minimal varint")
            return value, offset + 1
    raise ValueError("varint cut short")


def _hex(text: str, inline: bool) -> Multihash:
    """The lower-case hex of varint(code) + varint(length) + digest, nothing trailing."""
    if not HEX.fullmatch(text):
        raise ValueError("malformed hex multihash")
    raw = bytes.fromhex(text)
    code, at = _varint(raw, 0)
    length, at = _varint(raw, at)
    _checked(code, length, inline)
    if len(raw) - at != length:
        raise ValueError(f"digest length differs from {length}")
    return Multihash(code, raw[at:])


def spelling(text: str, *, inline: bool) -> Multihash:
    """The multihash a decimal spelling or its hex alias names. Refused (ValueError): a numeral
    with a leading zero or a non-ASCII digit, an unknown code, a digest of the wrong length,
    inline bytes over 32 or where `inline` is false, a number too large for its length, a
    non-minimal varint, trailing bytes."""
    return _decimal(text.split(":"), inline) if ":" in text else _hex(text, inline)
