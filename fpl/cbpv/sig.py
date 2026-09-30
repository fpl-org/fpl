"""A signature of constants: what the checker (and later the machine) knows about them.

Promised: nothing here says where a constant comes from. A first-order constant is a plain
function of its arguments' Python values (after `Const` unwrapping) and its call site, and
leaves its domain by returning a `Panic`, never by raising. An iterating constant runs a thunk
it receives; this module carries only its arity, which is what the checker reads (the
machine's `start` and `resume` land with the machine).
"""

from collections.abc import Callable, Hashable, Mapping
from dataclasses import dataclass

from fpl.cbpv.syntax import Position, Prim, Value, VType


@dataclass(frozen=True, slots=True)
class Panic:
    """A constant's refusal of arguments outside its domain; `payload` is its error."""

    payload: Hashable


@dataclass(frozen=True, slots=True)
class FirstOrder:
    """`⟨prim p, V₁ :: … :: Vₙ :: K⟩ ↦ ⟨return r, K⟩`, or a panic."""

    arity: int
    apply: Callable[[tuple[Hashable, ...], Position | None], Value | Panic]


@dataclass(frozen=True, slots=True)
class Iterating:
    """A constant that runs a thunk it is given `arity` arguments into its application."""

    arity: int


@dataclass(frozen=True, slots=True)
class Signature:
    """Σ: base types, constants, which instance types a constant admits, capabilities (base
    type to operation to argument and result type), and the payload type of `fail`."""

    bases: frozenset[str]
    constants: Mapping[str, FirstOrder | Iterating]
    admits: Callable[[Prim], bool]
    caps: Mapping[str, Mapping[str, tuple[VType, VType]]]
    fail_payload: VType
