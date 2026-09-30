"""The reference evaluator (design section 5): `run(program, machine, fuel)` steps a checked
program over x0..x30 and NZCV, the pc an instruction index, as the C6.2 pages' pseudocode does.

Promised: data processing by tables keyed on the op enums, operands by ShiftReg (J1.2.457)
and ExtendReg (J1.2.237), the bitfield moves by their pseudocode over DecodeBitMasks
(J1.2.214); NZCV by AddWithCarry (J1.4.396) and conditions by ConditionHolds (J1.4.541). A W
write zero-extends (`X{datasize}(d) = result`). Division by zero gives 0 and SDIV rounds
toward zero, `INT_MIN / -1` wrapping to INT_MIN (C6.2.357, C6.2.490); nothing traps.

Control stays within the program. `base` is the absolute address of instruction 0: `adr`, the
link of `bl` and `blr`, and register targets are addresses; a label is the index of the
instruction after it. A `br`, `blr` or `ret` to `base + 4i` with i in [0, n] continues at i,
and index n, past the last instruction, is falling off the end: `Halted`.

Memory is the window: `len(window)` bytes at the address in x28, read at each access. Every
addressing mode of LoadStore, LoadStoreUnscaled and Pair is evaluated, writeback included; an
access reads or writes little-endian bytes, and a misaligned one completes (hole
misaligned-access), as it does natively on Apple silicon at EL0.

Refused, as `Unmodelled(index, why)` at the instruction's index: a form that reads or writes
sp (the machine has none, hole sp-unobserved), an access with any byte outside the window,
and a register target anywhere else. `fuel` bounds the steps
executed; a program still running when it is spent is `OutOfFuel`.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import partial
from operator import add, invert, neg, sub
from typing import Any, NamedTuple, assert_never

import icontract

from fpl.asm.aarch64.check import addresses, check, slots
from fpl.asm.aarch64.model import (
    Addr,
    AddSubCarry,
    AddSubExtended,
    AddSubImm,
    AddSubShifted,
    Adr,
    Bitfield,
    Branch,
    BranchCond,
    BranchReg,
    CompareBranch,
    Cond,
    CondCompareImm,
    CondCompareReg,
    CondSelect,
    DataProc1,
    DataProc2,
    Extend,
    Extract,
    Instr,
    Label,
    LoadStore,
    LoadStoreUnscaled,
    LogicalImm,
    LogicalShifted,
    Mode,
    MoveWide,
    MulAdd,
    MulHigh,
    MulLong,
    Nop,
    Offset,
    OpAddSub,
    OpAddSubCarry,
    OpBitfield,
    OpBranch,
    OpBranchReg,
    OpCompareBranch,
    OpCondCompare,
    OpCondSelect,
    OpDataProc1,
    OpDataProc2,
    OpLoadStore,
    OpLoadStoreUnscaled,
    OpLogical,
    OpMoveWide,
    OpMulAdd,
    OpMulHigh,
    OpMulLong,
    OpPair,
    OpTestBranch,
    Pair,
    PostIndex,
    PreIndex,
    Program,
    Reg,
    RegOffset,
    Shift,
    TestBranch,
    Width,
)

REGISTERS = 31  # x0..x30; register 31 is sp or the zero register, neither a machine register


@dataclass(frozen=True, slots=True)
class Machine:
    """x0..x30 as values in [0, 2**64); NZCV as four bits, N the highest (C5.2.11); `base`,
    the absolute address of instruction 0 (from the run's record); `window`, the memory: its
    bytes at the address in x28, none by default, so every access falls outside it."""

    regs: tuple[int, ...]
    nzcv: int
    base: int
    window: bytes = b""


@dataclass(frozen=True, slots=True)
class Halted:
    """The program fell off its end in `machine`."""

    machine: Machine


@dataclass(frozen=True, slots=True)
class Unmodelled:
    """The instruction at index `index` (labels not counted) is outside the model: `why`."""

    index: int
    why: str


@dataclass(frozen=True, slots=True)
class OutOfFuel:
    """The fuel was spent before the program fell off its end."""


type Outcome = Halted | Unmodelled | OutOfFuel


def mask(bits: int) -> int:
    """The low `bits` bits set."""
    return (1 << bits) - 1


def sign(value: int, bits: int) -> int:
    """The low `bits` bits of `value` read as two's complement."""
    value &= mask(bits)
    return value - (1 << bits) if value >> (bits - 1) else value


def in_x(result: int) -> bool:
    """A register value: in [0, 2**64)."""
    return 0 <= result < 1 << 64


def fits(result: int, width: Width) -> bool:
    """Below 2**width: a W32 result has its upper 32 bits clear."""
    return result < 1 << width


@icontract.ensure(in_x)
@icontract.ensure(fits)
def written(value: int, width: Width) -> int:
    """`value` as a `width` result is written: its low `width` bits, zero-extended."""
    return value & mask(width)


def flags_in_range(result: tuple[int, int]) -> bool:
    """NZCV is four bits."""
    return 0 <= result[1] < 16


@icontract.ensure(flags_in_range)
def add_with_carry(x: int, y: int, carry: int, width: Width) -> tuple[int, int]:
    """AddWithCarry (J1.4.396): x + y + carry at `width` (x, y below 2**width, carry 0 or
    1), and the NZCV it sets."""
    unsigned_sum = x + y + carry
    signed_sum = sign(x, width) + sign(y, width) + carry
    result = unsigned_sum & mask(width)
    n, z = result >> (width - 1), result == 0
    c, v = result != unsigned_sum, sign(result, width) != signed_sum
    return result, n << 3 | z << 2 | c << 1 | v


class Flags(NamedTuple):
    """NZCV as four booleans."""

    n: bool
    z: bool
    c: bool
    v: bool


def flags(nzcv: int) -> Flags:
    """The four flags of `nzcv`."""
    return Flags(nzcv & 8 != 0, nzcv & 4 != 0, nzcv & 2 != 0, nzcv & 1 != 0)


# ConditionHolds (J1.4.541) by cond<3:1>; cond<0> set negates it, except for nv (true, as al).
CONDITIONS: tuple[Callable[[Flags], bool], ...] = (
    lambda f: f.z,  # eq, ne
    lambda f: f.c,  # hs, lo
    lambda f: f.n,  # mi, pl
    lambda f: f.v,  # vs, vc
    lambda f: f.c and not f.z,  # hi, ls
    lambda f: f.n == f.v,  # ge, lt
    lambda f: f.n == f.v and not f.z,  # gt, le
    lambda _: True,  # al, nv
)


def holds(cond: Cond, nzcv: int) -> bool:
    """ConditionHolds (J1.4.541)."""
    negated = cond & 1 == 1 and cond is not Cond.NV
    return CONDITIONS[cond >> 1](flags(nzcv)) != negated


def read(machine: Machine, reg: Reg, width: Width) -> int:
    """The low `width` bits of `reg`; the zero register reads 0."""
    return 0 if reg is Reg.ZR else machine.regs[reg] & mask(width)


def put(machine: Machine, reg: Reg, value: int, width: Width) -> Machine:
    """X{datasize}(d) = result: `value` written at `width`, so a W write clears the upper
    32 bits; the zero register discards it."""
    if reg is Reg.ZR:
        return machine
    regs = list(machine.regs)
    regs[reg] = written(value, width)
    return replace(machine, regs=tuple(regs))


def rotate(value: int, amount: int, width: int) -> int:
    """ROR: `value` (below 2**width) rotated right by `amount` in [0, width)."""
    return (value >> amount | value << (width - amount)) & mask(width)


# ShiftReg (J1.2.457) by shift, of a value below 2**width by an amount in [0, width).
SHIFTS: dict[Shift, Callable[[int, int, Width], int]] = {
    Shift.LSL: lambda value, amount, width: value << amount & mask(width),
    Shift.LSR: lambda value, amount, _: value >> amount,
    Shift.ASR: lambda value, amount, width: sign(value, width) >> amount & mask(width),
    Shift.ROR: rotate,
}

# ExtendReg (J1.2.237) by extend: (the low bits kept, sign-extended).
EXTENDS: dict[Extend, tuple[int, bool]] = {
    Extend.UXTB: (8, False),
    Extend.UXTH: (16, False),
    Extend.UXTW: (32, False),
    Extend.UXTX: (64, False),
    Extend.SXTB: (8, True),
    Extend.SXTH: (16, True),
    Extend.SXTW: (32, True),
    Extend.SXTX: (64, True),
}


def extend(value: int, how: Extend, amount: int, width: Width) -> int:
    """ExtendReg (J1.2.237): the kept low bits of `value` extended, shifted left `amount`."""
    size, signed = EXTENDS[how]
    kept = sign(value, size) if signed else value & mask(size)
    return kept << amount & mask(width)


# (NOT(operand2), sets NZCV) by op: SUB adds NOT(operand2) + 1, SBC NOT(operand2) + C.
ARITH: dict[OpAddSub | OpAddSubCarry, tuple[bool, bool]] = {
    OpAddSub.ADD: (False, False),
    OpAddSub.ADDS: (False, True),
    OpAddSub.SUB: (True, False),
    OpAddSub.SUBS: (True, True),
    OpAddSubCarry.ADC: (False, False),
    OpAddSubCarry.ADCS: (False, True),
    OpAddSubCarry.SBC: (True, False),
    OpAddSubCarry.SBCS: (True, True),
}

type Arith = AddSubImm | AddSubShifted | AddSubExtended | AddSubCarry


def arith(machine: Machine, i: Arith, operand: int, carry: int) -> Machine:
    """Rd = AddWithCarry(Rn, operand or NOT(operand), carry), NZCV by the flag-setting ops."""
    inverted, sets = ARITH[i.op]
    y = ~operand & mask(i.width) if inverted else operand
    result, nzcv = add_with_carry(read(machine, i.rn, i.width), y, carry, i.width)
    after = put(machine, i.rd, result, i.width)
    return replace(after, nzcv=nzcv) if sets else after


def add_sub(machine: Machine, i: AddSubImm | AddSubShifted | AddSubExtended, y: int) -> Machine:
    """ADD, ADDS, SUB, SUBS: the carry in is 1 exactly when subtracting."""
    return arith(machine, i, y, int(ARITH[i.op][0]))


def add_sub_imm(i: AddSubImm, machine: Machine) -> Machine:
    """C6.2.5, .10, .457, .464: the immediate, shifted 12 left by lsl12."""
    return add_sub(machine, i, i.imm << 12 * i.lsl12)


def add_sub_shifted(i: AddSubShifted, machine: Machine) -> Machine:
    """C6.2.6, .11, .458, .465: Rm by ShiftReg."""
    y = SHIFTS[i.shift](read(machine, i.rm, i.width), i.amount, i.width)
    return add_sub(machine, i, y)


def add_sub_extended(i: AddSubExtended, machine: Machine) -> Machine:
    """C6.2.4, .9, .456, .463: Rm by ExtendReg."""
    return add_sub(machine, i, extend(read(machine, i.rm, i.width), i.extend, i.amount, i.width))


def add_sub_carry(i: AddSubCarry, machine: Machine) -> Machine:
    """C6.2.2, .3, .352, .353: the carry in is C."""
    return arith(machine, i, read(machine, i.rm, i.width), flags(machine.nzcv).c)


def both(x: int, y: int) -> int:
    """AND."""
    return x & y


def either(x: int, y: int) -> int:
    """ORR."""
    return x | y


def differ(x: int, y: int) -> int:
    """EOR."""
    return x ^ y


# (operation, NOT(operand2)) by op; ANDS and BICS also set N and Z and clear C and V.
LOGICAL: dict[OpLogical, tuple[Callable[[int, int], int], bool]] = {
    OpLogical.AND: (both, False),
    OpLogical.BIC: (both, True),
    OpLogical.ORR: (either, False),
    OpLogical.ORN: (either, True),
    OpLogical.EOR: (differ, False),
    OpLogical.EON: (differ, True),
    OpLogical.ANDS: (both, False),
    OpLogical.BICS: (both, True),
}
LOGICAL_FLAGS = frozenset({OpLogical.ANDS, OpLogical.BICS})


def logical(machine: Machine, i: LogicalImm | LogicalShifted, y: int) -> Machine:
    """Rd = Rn op y (or NOT(y)); the immediate forms are the register ones' ops by name."""
    op = OpLogical(i.op)
    operation, inverted = LOGICAL[op]
    result = operation(read(machine, i.rn, i.width), ~y if inverted else y) & mask(i.width)
    after = put(machine, i.rd, result, i.width)
    if op not in LOGICAL_FLAGS:
        return after
    return replace(after, nzcv=(result >> (i.width - 1)) << 3 | (result == 0) << 2)


def logical_imm(i: LogicalImm, machine: Machine) -> Machine:
    """C6.2.14, .301, .155, .16: the model holds the immediate's value."""
    return logical(machine, i, i.imm)


def logical_shifted(i: LogicalShifted, machine: Machine) -> Machine:
    """C6.2.15 and the seven other logical (shifted register) pages: Rm by ShiftReg."""
    return logical(machine, i, SHIFTS[i.shift](read(machine, i.rm, i.width), i.amount, i.width))


# The new value by op, from the old one, the chunk imm16 << pos and pos (C6.2.283-.285).
MOVES: dict[OpMoveWide, Callable[[int, int, int], int]] = {
    OpMoveWide.MOVZ: lambda _, chunk, __: chunk,
    OpMoveWide.MOVN: lambda _, chunk, __: ~chunk,
    OpMoveWide.MOVK: lambda old, chunk, pos: old & ~(0xFFFF << pos) | chunk,
}


def move_wide(i: MoveWide, machine: Machine) -> Machine:
    """MOVZ, MOVN, MOVK; MOVK keeps the other chunks of the register read at the width."""
    pos = 16 * i.hw
    value = MOVES[i.op](read(machine, i.rd, i.width), i.imm16 << pos, pos)
    return put(machine, i.rd, value, i.width)


# (keeps the destination's other bits, sign-extends) by op (C6.2.39, .355, .487).
BITFIELDS: dict[OpBitfield, tuple[bool, bool]] = {
    OpBitfield.BFM: (True, False),
    OpBitfield.SBFM: (False, True),
    OpBitfield.UBFM: (False, False),
}


def bit_masks(immr: int, imms: int, width: Width) -> tuple[int, int]:
    """DecodeBitMasks (J1.2.214) with immediate FALSE and esize the width: (wmask, tmask)."""
    return rotate(mask(imms + 1), immr, width), mask((imms - immr) % width + 1)


def bitfield(i: Bitfield, machine: Machine) -> Machine:
    """BFM, SBFM, UBFM: bot from ROR(src, R) under wmask, top the destination or src<S>
    replicated, the two joined under tmask."""
    keeps, extends = BITFIELDS[i.op]
    wmask, tmask = bit_masks(i.immr, i.imms, i.width)
    src = read(machine, i.rn, i.width)
    dst = read(machine, i.rd, i.width) if keeps else 0
    bot = dst & ~wmask | rotate(src, i.immr, i.width) & wmask
    top = -(src >> i.imms & 1) if extends else dst
    return put(machine, i.rd, top & ~tmask | bot & tmask, i.width)


def extract(i: Extract, machine: Machine) -> Machine:
    """EXTR (C6.2.160): the width bits of Rn:Rm from lsb."""
    both = read(machine, i.rn, i.width) << i.width | read(machine, i.rm, i.width)
    return put(machine, i.rd, both >> i.lsb, i.width)


def variable(shift: Shift, x: int, y: int, width: Width) -> int:
    """LSLV, LSRV, ASRV, RORV: ShiftReg by Rm modulo the width."""
    return SHIFTS[shift](x, y % width, width)


def udiv(x: int, y: int, _: Width) -> int:
    """UDIV (C6.2.490): the quotient rounded down, 0 when y is 0."""
    return x // y if y else 0


def sdiv(x: int, y: int, width: Width) -> int:
    """SDIV (C6.2.357): the signed quotient rounded toward zero, 0 when y is 0; INT_MIN / -1
    is 2**(width - 1), which the write wraps to INT_MIN."""
    a, b = sign(x, width), sign(y, width)
    if b == 0:
        return 0
    quotient = abs(a) // abs(b)
    return quotient if (a < 0) == (b < 0) else -quotient


TWO: dict[OpDataProc2, Callable[[int, int, Width], int]] = {
    OpDataProc2.LSLV: partial(variable, Shift.LSL),
    OpDataProc2.LSRV: partial(variable, Shift.LSR),
    OpDataProc2.ASRV: partial(variable, Shift.ASR),
    OpDataProc2.RORV: partial(variable, Shift.ROR),
    OpDataProc2.SDIV: sdiv,
    OpDataProc2.UDIV: udiv,
}


def data_proc2(i: DataProc2, machine: Machine) -> Machine:
    """The two-source operations of Rn and Rm."""
    x, y = read(machine, i.rn, i.width), read(machine, i.rm, i.width)
    return put(machine, i.rd, TWO[i.op](x, y, i.width), i.width)


def reverse_bytes(size: int, value: int, width: int) -> int:
    """REV16, REV32, REV: the bytes of each `size`-byte container reversed."""
    data = value.to_bytes(width // 8, "big")
    chunks = (data[at : at + size][::-1] for at in range(0, len(data), size))
    return int.from_bytes(b"".join(chunks), "big")


def rev(value: int, width: int) -> int:
    """REV: the bytes of the whole width reversed."""
    return reverse_bytes(width // 8, value, width)


def rbit(value: int, width: int) -> int:
    """RBIT: the bits reversed."""
    return int(f"{value:0{width}b}"[::-1], 2)


def clz(value: int, width: int) -> int:
    """CountLeadingZeroBits."""
    return width - value.bit_length()


def cls(value: int, width: int) -> int:
    """CountLeadingSignBits: CountLeadingZeroBits(x<N-1:1> EOR x<N-2:0>)."""
    return clz((value >> 1) ^ (value & mask(width - 1)), width - 1)


ONE: dict[OpDataProc1, Callable[[int, int], int]] = {
    OpDataProc1.RBIT: rbit,
    OpDataProc1.REV16: partial(reverse_bytes, 2),
    OpDataProc1.REV: rev,
    OpDataProc1.REV32: partial(reverse_bytes, 4),
    OpDataProc1.CLZ: clz,
    OpDataProc1.CLS: cls,
}


def data_proc1(i: DataProc1, machine: Machine) -> Machine:
    """The one-source operations of Rn."""
    return put(machine, i.rd, ONE[i.op](read(machine, i.rn, i.width), i.width), i.width)


def factors(
    machine: Machine, i: MulAdd | MulLong | MulHigh, width: Width, *, signed: bool
) -> tuple[int, int]:
    """Rn and Rm at `width`, as two's complement when `signed`."""
    x, y = read(machine, i.rn, width), read(machine, i.rm, width)
    return (sign(x, width), sign(y, width)) if signed else (x, y)


ACCUMULATE: dict[OpMulAdd, Callable[[int, int], int]] = {OpMulAdd.MADD: add, OpMulAdd.MSUB: sub}
# (signed factors, accumulate) by op: X <- X[a] +/- W[n] * W[m] (C6.2.369, .378, .491, .497).
LONG: dict[OpMulLong, tuple[bool, Callable[[int, int], int]]] = {
    OpMulLong.SMADDL: (True, add),
    OpMulLong.SMSUBL: (True, sub),
    OpMulLong.UMADDL: (False, add),
    OpMulLong.UMSUBL: (False, sub),
}
HIGH: dict[OpMulHigh, bool] = {OpMulHigh.SMULH: True, OpMulHigh.UMULH: False}


def mul_add(i: MulAdd, machine: Machine) -> Machine:
    """MADD, MSUB (C6.2.275, .291): Ra +/- Rn * Rm."""
    x, y = factors(machine, i, i.width, signed=False)
    return put(machine, i.rd, ACCUMULATE[i.op](read(machine, i.ra, i.width), x * y), i.width)


def mul_long(i: MulLong, machine: Machine) -> Machine:
    """SMADDL, SMSUBL, UMADDL, UMSUBL: Xa +/- the 64-bit product of Wn and Wm."""
    signed, accumulate = LONG[i.op]
    x, y = factors(machine, i, Width.W32, signed=signed)
    return put(machine, i.rd, accumulate(read(machine, i.ra, Width.W64), x * y), Width.W64)


def mul_high(i: MulHigh, machine: Machine) -> Machine:
    """SMULH, UMULH (C6.2.379, .498): bits 127:64 of the 128-bit product."""
    x, y = factors(machine, i, Width.W64, signed=HIGH[i.op])
    return put(machine, i.rd, x * y >> 64, Width.W64)


# Rm transformed by op when the condition fails (C6.2.138, .141, .142, .143).
SELECT: dict[OpCondSelect, Callable[[int], int]] = {
    OpCondSelect.CSEL: lambda value: value,
    OpCondSelect.CSINC: lambda value: value + 1,
    OpCondSelect.CSINV: invert,
    OpCondSelect.CSNEG: neg,
}


def cond_select(i: CondSelect, machine: Machine) -> Machine:
    """Rd = Rn if the condition holds, else Rm through the op's transform."""
    if holds(i.cond, machine.nzcv):
        value = read(machine, i.rn, i.width)
    else:
        value = SELECT[i.op](read(machine, i.rm, i.width))
    return put(machine, i.rd, value, i.width)


def compare(machine: Machine, i: CondCompareReg | CondCompareImm, y: int) -> Machine:
    """CCMN and CCMP: NZCV by AddWithCarry when the condition holds (CCMP adds NOT(y) + 1),
    else the immediate nzcv (C6.2.79-.82)."""
    if not holds(i.cond, machine.nzcv):
        return replace(machine, nzcv=i.nzcv)
    subtracts = i.op is OpCondCompare.CCMP
    operand = ~y & mask(i.width) if subtracts else y
    _, nzcv = add_with_carry(read(machine, i.rn, i.width), operand, int(subtracts), i.width)
    return replace(machine, nzcv=nzcv)


def cond_compare_reg(i: CondCompareReg, machine: Machine) -> Machine:
    """CCMN, CCMP (register): against Rm."""
    return compare(machine, i, read(machine, i.rm, i.width))


def cond_compare_imm(i: CondCompareImm, machine: Machine) -> Machine:
    """CCMN, CCMP (immediate): against imm5."""
    return compare(machine, i, i.imm5)


def nop(_: Nop, machine: Machine) -> Machine:
    """NOP (C6.2.299)."""
    return machine


# The data-processing classes: the machine after the instruction; the pc moves on by one.
DATA: dict[type, Callable[[Any, Machine], Machine]] = {
    AddSubImm: add_sub_imm,
    AddSubShifted: add_sub_shifted,
    AddSubExtended: add_sub_extended,
    AddSubCarry: add_sub_carry,
    LogicalImm: logical_imm,
    LogicalShifted: logical_shifted,
    MoveWide: move_wide,
    Bitfield: bitfield,
    Extract: extract,
    DataProc2: data_proc2,
    DataProc1: data_proc1,
    MulAdd: mul_add,
    MulLong: mul_long,
    MulHigh: mul_high,
    CondSelect: cond_select,
    CondCompareReg: cond_compare_reg,
    CondCompareImm: cond_compare_imm,
    Nop: nop,
}


@dataclass(frozen=True, slots=True)
class Place:
    """Where an instruction runs: its index, each label's instruction index, and the number
    of instructions (the index past the last, where the program halts)."""

    index: int
    labels: dict[str, int]
    end: int


type Stepped = tuple[Machine, int] | str  # the machine and the next index, or why Unmodelled


def link(machine: Machine, place: Place) -> Machine:
    """x30 = the address of the next instruction (BL, BLR)."""
    return put(machine, Reg.X30, machine.base + 4 * (place.index + 1), Width.W64)


def taken(place: Place, target: Label, *, jumps: bool) -> int:
    """The label's index when the branch is taken, else the next one."""
    return place.labels[target.name] if jumps else place.index + 1


def branch(i: Branch, machine: Machine, place: Place) -> Stepped:
    """B, BL (C6.2.35, .43)."""
    linked = link(machine, place) if i.op is OpBranch.BL else machine
    return linked, place.labels[i.target.name]


def branch_cond(i: BranchCond, machine: Machine, place: Place) -> Stepped:
    """B.cond (C6.2.34)."""
    return machine, taken(place, i.target, jumps=holds(i.cond, machine.nzcv))


def compare_branch(i: CompareBranch, machine: Machine, place: Place) -> Stepped:
    """CBZ, CBNZ (C6.2.78, .77): Rt at the width against zero."""
    zero = read(machine, i.rt, i.width) == 0
    return machine, taken(place, i.target, jumps=zero == (i.op is OpCompareBranch.CBZ))


def bit_branch(i: TestBranch, machine: Machine, place: Place) -> Stepped:
    """TBZ, TBNZ (C6.2.479, .478): bit `bit` of Xt."""
    clear = not read(machine, i.rt, Width.W64) >> i.bit & 1
    return machine, taken(place, i.target, jumps=clear == (i.op is OpTestBranch.TBZ))


def adr(i: Adr, machine: Machine, place: Place) -> Stepped:
    """ADR (C6.2.12): the label's absolute address."""
    address = machine.base + 4 * place.labels[i.target.name]
    return put(machine, i.rd, address, Width.W64), place.index + 1


def branch_reg(i: BranchReg, machine: Machine, place: Place) -> Stepped:
    """BR, BLR, RET (C6.2.46, .44, .338): to base + 4i with i in [0, n], the target read
    before BLR links."""
    target = read(machine, i.rn, Width.W64)
    index, off = divmod(target - machine.base, 4)
    if off or not 0 <= index <= place.end:
        return f"{i.op} to {target:#x}, not base + 4i with i in [0, {place.end}]"
    return (link(machine, place) if i.op is OpBranchReg.BLR else machine), index


OUTSIDE = "memory access outside the window"
STORE, LOAD, SIGNED = "store", "load", "signed"

# What each single-register op transfers: a store, a load, or a sign-extending load.
TRANSFERS: dict[OpLoadStore | OpLoadStoreUnscaled, str] = {
    OpLoadStore.STRB: STORE,
    OpLoadStore.LDRB: LOAD,
    OpLoadStore.LDRSB_W: SIGNED,
    OpLoadStore.LDRSB_X: SIGNED,
    OpLoadStore.STRH: STORE,
    OpLoadStore.LDRH: LOAD,
    OpLoadStore.LDRSH_W: SIGNED,
    OpLoadStore.LDRSH_X: SIGNED,
    OpLoadStore.STR_W: STORE,
    OpLoadStore.STR_X: STORE,
    OpLoadStore.LDR_W: LOAD,
    OpLoadStore.LDR_X: LOAD,
    OpLoadStore.LDRSW: SIGNED,
    OpLoadStoreUnscaled.STURB: STORE,
    OpLoadStoreUnscaled.STURH: STORE,
    OpLoadStoreUnscaled.STUR_W: STORE,
    OpLoadStoreUnscaled.STUR_X: STORE,
    OpLoadStoreUnscaled.LDURB: LOAD,
    OpLoadStoreUnscaled.LDURH: LOAD,
    OpLoadStoreUnscaled.LDURSB_W: SIGNED,
    OpLoadStoreUnscaled.LDURSB_X: SIGNED,
    OpLoadStoreUnscaled.LDURSH_W: SIGNED,
    OpLoadStoreUnscaled.LDURSH_X: SIGNED,
    OpLoadStoreUnscaled.LDUR_W: LOAD,
    OpLoadStoreUnscaled.LDUR_X: LOAD,
    OpLoadStoreUnscaled.LDURSW: SIGNED,
}
PAIRED: dict[OpPair, str] = {OpPair.STP: STORE, OpPair.LDP: LOAD, OpPair.LDPSW: SIGNED}
MODES: dict[Mode, Callable[[Reg, int], Addr]] = {
    Mode.OFFSET: Offset,
    Mode.PRE: PreIndex,
    Mode.POST: PostIndex,
}


class Transfer(NamedTuple):
    """One register's transfer: its kind (STORE, LOAD, SIGNED), the bytes, the register width."""

    kind: str
    size: int
    width: Width


def displaced(machine: Machine, rn: Reg, by: int) -> int:
    """Xn + by, modulo 2**64."""
    return (read(machine, rn, Width.W64) + by) & mask(64)


def effective(machine: Machine, addr: Addr, size: int) -> tuple[int, int | None]:
    """The address accessed and the base written back (None without writeback): an offset
    or pre-index accesses Xn + imm, a post-index Xn; a register offset adds Rm by ExtendReg,
    shifted log2(size) when S is set."""
    match addr:
        case Offset(rn=rn, imm=imm):
            return displaced(machine, rn, imm), None
        case PreIndex(rn=rn, imm=imm):
            moved = displaced(machine, rn, imm)
            return moved, moved
        case PostIndex(rn=rn, imm=imm):
            return read(machine, rn, Width.W64), displaced(machine, rn, imm)
        case RegOffset(rn=rn, rm=rm, option=option, s=s):
            amount = size.bit_length() - 1 if s else 0
            index = extend(read(machine, rm, Width.W64), option, amount, Width.W64)
            return displaced(machine, rn, index), None
        case _:
            assert_never(addr)


def inside(machine: Machine, address: int, count: int) -> int | None:
    """The window offset of the `count` bytes at `address`, or None when any is outside."""
    at = address - read(machine, Reg.X28, Width.W64)
    return at if 0 <= at <= len(machine.window) - count else None


def transfer(machine: Machine, how: Transfer, rt: Reg, at: int) -> Machine:
    """Rt's low `size` bytes stored at window offset `at`, or loaded from there, zero- or
    sign-extended, and written at the width; little-endian either way."""
    if how.kind == STORE:
        data = (read(machine, rt, how.width) & mask(8 * how.size)).to_bytes(how.size, "little")
        return replace(machine, window=machine.window[:at] + data + machine.window[at + how.size :])
    value = int.from_bytes(machine.window[at : at + how.size], "little")
    return put(
        machine,
        rt,
        sign(value, 8 * how.size) if how.kind == SIGNED else value,
        how.width,
    )


def written_back(machine: Machine, rn: Reg, base: int | None) -> Machine:
    """Xn = the new base after a pre- or post-index access; unchanged without writeback."""
    return machine if base is None else put(machine, rn, base, Width.W64)


def single(
    machine: Machine, op: OpLoadStore | OpLoadStoreUnscaled, rt: Reg, address: int
) -> Machine | None:
    """One register transferred by `op` at `address`, or None outside the window."""
    at = inside(machine, address, op.size)
    return (
        None
        if at is None
        else transfer(machine, Transfer(TRANSFERS[op], op.size, op.width), rt, at)
    )


def load_store(i: LoadStore, machine: Machine, place: Place) -> Stepped:
    """LDR, STR and their B, H, SB, SH, SW forms, every addressing mode, writeback after the
    access (C6.2.216 and the other LoadStore pages)."""
    address, base = effective(machine, i.addr, i.op.size)
    after = single(machine, i.op, i.rt, address)
    return OUTSIDE if after is None else (written_back(after, i.addr.rn, base), place.index + 1)


def unscaled(i: LoadStoreUnscaled, machine: Machine, place: Place) -> Stepped:
    """LDUR, STUR and their forms (C6.2.259-.264, .446-.448): Xn + simm9."""
    after = single(machine, i.op, i.rt, displaced(machine, i.rn, i.simm9))
    return OUTSIDE if after is None else (after, place.index + 1)


def pair(i: Pair, machine: Machine, place: Place) -> Stepped:
    """STP, LDP, LDPSW (C6.2.414, .214, .215): Rt at the address, Rt2 at the next `size`
    bytes, in each mode; LDPSW sign-extends its words to 64 bits."""
    size = 4 if i.op is OpPair.LDPSW else i.width // 8
    address, base = effective(machine, MODES[i.mode](i.rn, i.imm), size)
    at = inside(machine, address, 2 * size)
    if at is None:
        return OUTSIDE
    how = Transfer(PAIRED[i.op], size, i.width)
    after = transfer(transfer(machine, how, i.rt, at), how, i.rt2, at + size)
    return written_back(after, i.rn, base), place.index + 1


CONTROL: dict[type, Callable[[Any, Machine, Place], Stepped]] = {
    Branch: branch,
    BranchCond: branch_cond,
    CompareBranch: compare_branch,
    TestBranch: bit_branch,
    Adr: adr,
    BranchReg: branch_reg,
    LoadStore: load_store,
    LoadStoreUnscaled: unscaled,
    Pair: pair,
}


def step(instr: Instr, machine: Machine, place: Place) -> Stepped:
    """One instruction: the machine after it and the next index, or why it is Unmodelled."""
    if any(reg is Reg.SP for _, _, reg in slots(instr)):
        return f"{type(instr).__name__} uses sp, which the machine does not have"
    if type(instr) in DATA:
        return DATA[type(instr)](instr, machine), place.index + 1
    return CONTROL[type(instr)](instr, machine, place)


def runnable(program: Program, machine: Machine) -> bool:
    """A checked program, and a machine of 31 register values and four flag bits."""
    shaped = len(machine.regs) == REGISTERS and all(map(in_x, machine.regs))
    return shaped and 0 <= machine.nzcv < 16 and check(program) == ()


def keeps_base(machine: Machine, result: Outcome) -> bool:
    """A halted machine has the base it started with."""
    return not isinstance(result, Halted) or result.machine.base == machine.base


@icontract.require(runnable)
@icontract.ensure(keeps_base)
def run(program: Program, machine: Machine, fuel: int) -> Outcome:
    """Run `program` from index 0 on `machine` for at most `fuel` instructions."""
    code = [item for item in program if not isinstance(item, Label)]
    labels = {name: address // 4 for name, address in addresses(program).items()}
    index = 0
    for _ in range(fuel):
        if index == len(code):
            return Halted(machine)
        stepped = step(code[index], machine, Place(index, labels, len(code)))
        if isinstance(stepped, str):
            return Unmodelled(index, stepped)
        machine, index = stepped
    return Halted(machine) if index == len(code) else OutOfFuel()
