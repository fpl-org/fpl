"""The instructions of WebAssembly, spec 2.4, for the subset of `fpl.asm.wasm`.

One frozen dataclass per production of the grammar, carrying its number type and operator
(2.4.8 writes `numtype.binop`); operator names are Literal strings, printed as they are. So
far: the parametric (2.4.1), variable (2.4.3) and integer numeric (2.4.8) instructions, and
control (2.4.2) with tail calls.

A class whose fields are typed by a Literal guards its invariant in `__post_init__`, not with
`icontract.invariant`: CrossHair 0.0.110 cannot build a symbolic Literal and crashes on any
contract that reaches one (HOLES.md, crosshair-literal). Each guard is a named predicate and
refuses a value that breaks it with ValueError, so such a value never exists.
"""

from dataclasses import dataclass
from typing import Literal

from fpl.asm.wasm.types import WIDTH, BlockType, NumType, TypeUse, ValType

IUnop = Literal["clz", "ctz", "popcnt", "extend8_s", "extend16_s", "extend32_s"]
"""2.4.8, the integer unary operators; extend32_s exists on i64 only."""

IBinop = Literal[
    "add", "sub", "mul", "div_s", "div_u", "rem_s", "rem_u",
    "and", "or", "xor", "shl", "shr_s", "shr_u", "rotl", "rotr",
]  # fmt: skip
"""2.4.8, the integer binary operators."""

ITestop = Literal["eqz"]
"""2.4.8, the integer test operators."""

IRelop = Literal["eq", "ne", "lt_s", "lt_u", "gt_s", "gt_u", "le_s", "le_u", "ge_s", "ge_u"]
"""2.4.8, the integer relational operators."""

ICvtop = Literal["wrap", "extend_s", "extend_u"]
"""2.4.8, the integer conversions: i32.wrap_i64, i64.extend_i32_s, i64.extend_i32_u."""


def _refuse(ok: bool, what: str) -> None:
    """Raise ValueError naming `what` unless `ok`: the guard every `__post_init__` shares."""
    if not ok:
        raise ValueError(what)


def const_in_range(self: "Const") -> bool:
    """A constant is unsigned and fits its type: 0 <= value < 2**N (4.3.1)."""
    return 0 <= self.value < 1 << WIDTH[self.type]


def unop_fits(self: "Unop") -> bool:
    """`extend32_s` narrows from 32 bits, so it exists on i64 only (2.4.8)."""
    return self.op != "extend32_s" or self.type == "i64"


def cvtop_shape(self: "Cvtop") -> bool:
    """`wrap` goes from i64 to i32, `extend_s` and `extend_u` from i32 to i64 (2.4.8)."""
    return (self.to, self.source) == (("i32", "i64") if self.op == "wrap" else ("i64", "i32"))


@dataclass(frozen=True, slots=True)
class Const:
    """2.4.8, `t.const c`: the value unsigned, as the abstract syntax holds it.

    Refuses, with ValueError, a value outside 0 <= value < 2**N.
    """

    type: NumType
    value: int

    def __post_init__(self) -> None:
        range_ = f"0 <= value < 2**{WIDTH[self.type]}"
        _refuse(const_in_range(self), f"{self.type}.const {self.value} is outside {range_}")


@dataclass(frozen=True, slots=True)
class Unop:
    """2.4.8, `t.unop`: pops one operand of type t, pushes one. Refuses i32.extend32_s."""

    type: NumType
    op: IUnop

    def __post_init__(self) -> None:
        _refuse(unop_fits(self), f"{self.type}.{self.op} does not exist")


@dataclass(frozen=True, slots=True)
class Binop:
    """2.4.8, `t.binop`: pops two operands of type t, pushes one."""

    type: NumType
    op: IBinop


@dataclass(frozen=True, slots=True)
class Testop:
    """2.4.8, `t.testop`: pops one operand of type t, pushes an i32."""

    type: NumType
    op: ITestop


@dataclass(frozen=True, slots=True)
class Relop:
    """2.4.8, `t.relop`: pops two operands of type t, pushes an i32."""

    type: NumType
    op: IRelop


@dataclass(frozen=True, slots=True)
class Cvtop:
    """2.4.8, `to.cvtop_source`: converts an operand of type `source` to type `to`.

    Refuses every shape but i32.wrap_i64 and i64.extend_i32_s/u.
    """

    to: NumType
    op: ICvtop
    source: NumType

    def __post_init__(self) -> None:
        _refuse(cvtop_shape(self), f"{self.to}.{self.op} from {self.source} does not exist")


@dataclass(frozen=True, slots=True)
class Nop:
    """2.4.1, `nop`: does nothing."""


@dataclass(frozen=True, slots=True)
class Unreachable:
    """2.4.1, `unreachable`: traps."""


@dataclass(frozen=True, slots=True)
class Drop:
    """2.4.1, `drop`: pops one operand."""


@dataclass(frozen=True, slots=True)
class Select:
    """2.4.1, `select`: plain when `types` is None, else typed `select (result t*)`."""

    types: tuple[ValType, ...] | None


@dataclass(frozen=True, slots=True)
class LocalGet:
    """2.4.3, `local.get x`."""

    index: int


@dataclass(frozen=True, slots=True)
class LocalSet:
    """2.4.3, `local.set x`."""

    index: int


@dataclass(frozen=True, slots=True)
class LocalTee:
    """2.4.3, `local.tee x`: sets the local and keeps the operand."""

    index: int


@dataclass(frozen=True, slots=True)
class GlobalGet:
    """2.4.3, `global.get x`."""

    index: int


@dataclass(frozen=True, slots=True)
class GlobalSet:
    """2.4.3, `global.set x`."""

    index: int


@dataclass(frozen=True, slots=True)
class Return:
    """2.4.2, `return`: leaves the function with its results."""


@dataclass(frozen=True, slots=True)
class Block:
    """2.4.2, `block bt instr* end`: a branch to it continues after its end."""

    type: BlockType
    body: "tuple[Instr, ...]"


@dataclass(frozen=True, slots=True)
class Loop:
    """2.4.2, `loop bt instr* end`: a branch to it continues at its start."""

    type: BlockType
    body: "tuple[Instr, ...]"


@dataclass(frozen=True, slots=True)
class If:
    """2.4.2, `if bt instr* else instr* end`: pops an i32 and runs `then` unless it is 0."""

    type: BlockType
    then: "tuple[Instr, ...]"
    else_: "tuple[Instr, ...]"


@dataclass(frozen=True, slots=True)
class Br:
    """2.4.2, `br l`: branches to the l-th enclosing label, 0 the innermost."""

    label: int


@dataclass(frozen=True, slots=True)
class BrIf:
    """2.4.2, `br_if l`: pops an i32 and branches to label l unless it is 0."""

    label: int


@dataclass(frozen=True, slots=True)
class BrTable:
    """2.4.2, `br_table l* l_N`: pops an i32 i and branches to `labels[i]`, else to `default`."""

    labels: tuple[int, ...]
    default: int


@dataclass(frozen=True, slots=True)
class Call:
    """2.4.2, `call x`: calls function x."""

    func: int


@dataclass(frozen=True, slots=True)
class CallIndirect:
    """2.4.2, `call_indirect x y`: pops an i32 i and calls table x's element i at type y."""

    table: int
    type: TypeUse


@dataclass(frozen=True, slots=True)
class ReturnCall:
    """2.4.2, `return_call x`: a tail call of function x; the caller's frame is gone."""

    func: int


@dataclass(frozen=True, slots=True)
class ReturnCallIndirect:
    """2.4.2, `return_call_indirect x y`: the tail-call form of `call_indirect x y`."""

    table: int
    type: TypeUse


Instr = (
    Const | Unop | Binop | Testop | Relop | Cvtop
    | Nop | Unreachable | Drop | Select
    | LocalGet | LocalSet | LocalTee | GlobalGet | GlobalSet
    | Block | Loop | If | Br | BrIf | BrTable | Return
    | Call | CallIndirect | ReturnCall | ReturnCallIndirect
)  # fmt: skip
"""A closed union of the instructions; a match on it is checked for exhaustiveness."""
