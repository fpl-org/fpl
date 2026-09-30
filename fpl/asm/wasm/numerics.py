"""The integer operators of WebAssembly, spec 4.3.2, for the subset of `fpl.asm.wasm`.

Values are unsigned, 0 <= i < 2**N (4.3.1); the signed reading of an operator goes through
`signed`. Every operator is a pure function of the width N and its operands; the two that can
fail return a `Trap` as a value, never raise. The tables are keyed by the operator Literals of
`fpl.asm.wasm.instr`, so an operator has exactly one definition.

`Trap` and `TrapKind` live here, not in `exec.py`: the integer operators are the first to
return one, and the evaluator's `Outcome` reuses the class.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from fpl.asm.wasm.instr import IBinop, ICvtop, IRelop, ITestop, IUnop

TrapKind = Literal[
    "unreachable",
    "integer divide by zero",
    "integer overflow",
    "indirect call type mismatch",
    "uninitialized element",
    "undefined element",
    "out of bounds memory access",
    "out of bounds table access",
]
"""What trapped, in the words wasmtime and wabt use (the last only at instantiation)."""


@dataclass(frozen=True, slots=True)
class Trap:
    """4.4.1, a trap: the run stops, and `kind` says why."""

    kind: TrapKind


def signed(n: int, i: int) -> int:
    """4.3.1, signed_N: the two's complement reading of the unsigned `i`."""
    return i - (1 << n) if i >> (n - 1) else i


def _wrap(n: int, i: int) -> int:
    """i modulo 2**N: the unsigned value of any Python integer."""
    return i & ((1 << n) - 1)


def _extend(m: int) -> Callable[[int, int], int]:
    """4.3.2, iextendM_s: the low M bits of i, sign-extended to N."""
    return lambda n, i: _wrap(n, signed(m, _wrap(m, i)))


def _ctz(n: int, i: int) -> int:
    """4.3.2, ictz: the trailing zero bits of i; N for 0."""
    return (i & -i).bit_length() - 1 if i else n


UNOPS: dict[IUnop, Callable[[int, int], int]] = {
    "clz": lambda n, i: n - i.bit_length(),
    "ctz": _ctz,
    "popcnt": lambda _n, i: i.bit_count(),
    "extend8_s": _extend(8),
    "extend16_s": _extend(16),
    "extend32_s": _extend(32),
}
"""4.3.2, the unary operators: (N, i) to a result."""


def _quotient(a: int, b: int) -> int:
    """a / b rounded toward zero, as trunc does in 4.3.2 (Python's // rounds down)."""
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def _div_u(_n: int, i: int, j: int) -> int | Trap:
    """4.3.2, idiv_u: traps on a zero divisor."""
    return Trap("integer divide by zero") if j == 0 else i // j


def _div_s(n: int, i: int, j: int) -> int | Trap:
    """4.3.2, idiv_s: traps on a zero divisor, and on -2**(N-1) / -1, whose quotient is 2**(N-1)."""
    if j == 0:
        return Trap("integer divide by zero")
    q = _quotient(signed(n, i), signed(n, j))
    return Trap("integer overflow") if q == 1 << (n - 1) else _wrap(n, q)


def _rem_u(_n: int, i: int, j: int) -> int | Trap:
    """4.3.2, irem_u: traps on a zero divisor."""
    return Trap("integer divide by zero") if j == 0 else i % j


def _rem_s(n: int, i: int, j: int) -> int | Trap:
    """4.3.2, irem_s: traps on a zero divisor; the remainder takes the dividend's sign."""
    if j == 0:
        return Trap("integer divide by zero")
    a, b = signed(n, i), signed(n, j)
    return _wrap(n, a - b * _quotient(a, b))


def _rotl(n: int, i: int, j: int) -> int:
    """4.3.2, irotl: rotates left by j modulo N."""
    k = j % n
    return _wrap(n, i << k | i >> (n - k))


def _rotr(n: int, i: int, j: int) -> int:
    """4.3.2, irotr: rotates right by j modulo N."""
    k = j % n
    return _wrap(n, i >> k | i << (n - k))


BINOPS: dict[IBinop, Callable[[int, int, int], int | Trap]] = {
    "add": lambda n, i, j: _wrap(n, i + j),
    "sub": lambda n, i, j: _wrap(n, i - j),
    "mul": lambda n, i, j: _wrap(n, i * j),
    "div_s": _div_s,
    "div_u": _div_u,
    "rem_s": _rem_s,
    "rem_u": _rem_u,
    "and": lambda _n, i, j: i & j,
    "or": lambda _n, i, j: i | j,
    "xor": lambda _n, i, j: i ^ j,
    "shl": lambda n, i, j: _wrap(n, i << (j % n)),
    "shr_s": lambda n, i, j: _wrap(n, signed(n, i) >> (j % n)),
    "shr_u": lambda n, i, j: i >> (j % n),
    "rotl": _rotl,
    "rotr": _rotr,
}
"""4.3.2, the binary operators: (N, i, j) to a result, or a Trap."""

TESTOPS: dict[ITestop, Callable[[int, int], int]] = {
    "eqz": lambda _n, i: int(i == 0),
}
"""4.3.2, the test operators: (N, i) to an i32 truth value."""

RELOPS: dict[IRelop, Callable[[int, int, int], int]] = {
    "eq": lambda _n, i, j: int(i == j),
    "ne": lambda _n, i, j: int(i != j),
    "lt_u": lambda _n, i, j: int(i < j),
    "gt_u": lambda _n, i, j: int(i > j),
    "le_u": lambda _n, i, j: int(i <= j),
    "ge_u": lambda _n, i, j: int(i >= j),
    "lt_s": lambda n, i, j: int(signed(n, i) < signed(n, j)),
    "gt_s": lambda n, i, j: int(signed(n, i) > signed(n, j)),
    "le_s": lambda n, i, j: int(signed(n, i) <= signed(n, j)),
    "ge_s": lambda n, i, j: int(signed(n, i) >= signed(n, j)),
}
"""4.3.2, the relational operators: (N, i, j) to an i32 truth value."""

CVTOPS: dict[ICvtop, Callable[[int], int]] = {
    "wrap": lambda i: _wrap(32, i),
    "extend_s": lambda i: _wrap(64, signed(32, i)),
    "extend_u": lambda i: i,
}
"""4.3.2, the conversions: i32.wrap_i64, i64.extend_i32_s, i64.extend_i32_u, of one operand."""
