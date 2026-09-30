"""A signature of constants: what the checker and the machine know about them.

Promised: nothing here says where a constant comes from. A first-order constant is a plain
function of its arguments' Python values (after `Const` unwrapping) and its call site, and
leaves its domain by returning a `Panic`, never by raising. An iterating constant runs a thunk
it receives: `start` answers its arguments with a `Call` of that thunk (the machine keeps the
loop as a frame and hands what the thunk returns to `resume`), a `Done` result, or a `Panic`.

Arguments reach a constant top of stack first: after `App(V₁, App(V₂, prim p))` the stack is
`V₂ :: V₁ :: K`, so `p` receives `(V₂, V₁)`, its arrow's parameters in order. The values an
iterating constant receives and returns are those of whichever machine runs it (the
environment machine's closures, or the literal CK machine's thunks); it passes thunks on
without looking inside them.
"""

from collections.abc import Callable, Hashable, Mapping
from dataclasses import dataclass
from typing import Any

from fpl.cbpv.syntax import Const, Position, Prim, Value, VType


@dataclass(frozen=True, slots=True)
class Panic:
    """A constant's refusal of arguments outside its domain; `payload` is its error."""

    payload: Hashable


@dataclass(frozen=True, slots=True)
class Call:
    """Run `thunk` with `args` pushed (top first), then resume from `state` with its result."""

    thunk: Any
    args: tuple[Any, ...]
    state: Any


@dataclass(frozen=True, slots=True)
class Done:
    """The iterating constant returns `value`."""

    value: Const


type Step = Call | Done


@dataclass(frozen=True, slots=True)
class FirstOrder:
    """`⟨prim p, V₁ :: … :: Vₙ :: K⟩ ↦ ⟨return r, K⟩`, or a panic."""

    arity: int
    apply: Callable[[tuple[Hashable, ...], Position | None], Value | Panic]


@dataclass(frozen=True, slots=True)
class Iterating:
    """A constant that runs a thunk among its `arity` arguments, as a loop the machine keeps:
    `⟨prim p, V₁ :: … :: Vₙ :: K⟩` steps by `start`, `⟨return V, loop(p, s) :: K⟩` by
    `resume(s, V)` (hole iteration-constants)."""

    arity: int
    start: Callable[[tuple[Any, ...], Position | None], Step | Panic]
    resume: Callable[[Any, Any], Step | Panic]


@dataclass(frozen=True, slots=True)
class Signature:
    """Σ: base types, constants, which instance types a constant admits, capabilities (base
    type to operation to argument and result type), and the payload type of `fail`."""

    bases: frozenset[str]
    constants: Mapping[str, FirstOrder | Iterating]
    admits: Callable[[Prim], bool]
    caps: Mapping[str, Mapping[str, tuple[VType, VType]]]
    fail_payload: VType
