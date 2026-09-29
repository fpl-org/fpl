"""The reference evaluator: what an RV64IM program does to the integer registers, purely.

`run(program, machine, base, fuel)` executes the program's instructions from the first, one
step each, and says how it ended: `Halted` on falling off the end, `Trapped` on ecall or ebreak,
`Unmodelled` at an instruction whose effect the evaluator does not know, `OutOfFuel` when
`fuel` steps did not reach an end. It never raises on a program the model can hold.

Register values are unsigned 64-bit ints, as QEMU reports them. `u64` wraps a Python int
into that range, `sext` sign-extends its low bits into it, and `signed` reads its low bits as
two's complement, the one reading the signed operations need. Semantics are tables keyed by
the op enums, one row per mnemonic. The W forms compute on the low 32 bits and sign-extend
the 32-bit result (4.2.1, 4.2.2), as do `lui` and `auipc` for their 32-bit immediate (4.2.1).
Division by zero and signed overflow follow Table 11 and never trap (12.2).

The pc is an instruction index: labels take no space, every instruction is 4 bytes. `base`
is the absolute address of instruction 0, which `auipc` adds. Trapped and Unmodelled carry
the instruction index of the instruction they stopped at.

The system instructions follow the QEMU virt EEI in M-mode on one hart: ecall is cause 11
(environment call from M-mode), ebreak cause 3 (breakpoint), and fence and fence.tso order
nothing. Loads and stores are not modelled.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import assert_never

from fpl.asm.riscv.model import (
    Bare,
    Branch,
    Fence,
    I,
    Instr,
    Jal,
    Jalr,
    Label,
    Load,
    OpBare,
    OpI,
    OpR,
    OpShift,
    OpUpper,
    Program,
    R,
    Reg,
    Shift,
    Store,
    Upper,
)

LOW64 = (1 << 64) - 1
LOW32 = (1 << 32) - 1


def u64(value: int) -> int:
    """`value` modulo 2**64: the register value with the same low 64 bits."""
    return value & LOW64


def signed(value: int, bits: int) -> int:
    """The low `bits` bits of `value` read as a two's-complement number."""
    low = value & ((1 << bits) - 1)
    return low - (1 << bits) if low >> (bits - 1) else low


def sext(value: int, bits: int) -> int:
    """The low `bits` bits of `value` sign-extended to a 64-bit register value."""
    return u64(signed(value, bits))


def quotient(x: int, y: int) -> int:
    """`x / y` rounded toward zero (12.2), and -1, all ones, for a zero divisor (Table 11).

    Signed overflow needs no case of its own: `-2**(L-1) / -1` is `2**(L-1)`, which the caller
    wraps to the dividend at width L, as Table 11 says.
    """
    if y == 0:
        return -1
    magnitude = abs(x) // abs(y)
    return magnitude if (x < 0) == (y < 0) else -magnitude


def remainder(x: int, y: int) -> int:
    """The remainder with the dividend's sign; the dividend for a zero divisor (Table 11)."""
    return x - y * quotient(x, y)


# Register-register operations on two register values (2.4.2, 4.2.2, 12.1, 12.2).
ALU: dict[OpR, Callable[[int, int], int]] = {
    OpR.ADD: lambda a, b: u64(a + b),
    OpR.SUB: lambda a, b: u64(a - b),
    OpR.SLL: lambda a, b: u64(a << (b & 63)),
    OpR.SLT: lambda a, b: int(signed(a, 64) < signed(b, 64)),
    OpR.SLTU: lambda a, b: int(a < b),
    OpR.XOR: lambda a, b: a ^ b,
    OpR.SRL: lambda a, b: a >> (b & 63),
    OpR.SRA: lambda a, b: u64(signed(a, 64) >> (b & 63)),
    OpR.OR: lambda a, b: a | b,
    OpR.AND: lambda a, b: a & b,
    OpR.ADDW: lambda a, b: sext(a + b, 32),
    OpR.SUBW: lambda a, b: sext(a - b, 32),
    OpR.SLLW: lambda a, b: sext(a << (b & 31), 32),
    OpR.SRLW: lambda a, b: sext((a & LOW32) >> (b & 31), 32),
    OpR.SRAW: lambda a, b: sext(signed(a, 32) >> (b & 31), 32),
    OpR.MUL: lambda a, b: u64(a * b),
    OpR.MULH: lambda a, b: u64((signed(a, 64) * signed(b, 64)) >> 64),
    OpR.MULHSU: lambda a, b: u64((signed(a, 64) * b) >> 64),
    OpR.MULHU: lambda a, b: (a * b) >> 64,
    OpR.DIV: lambda a, b: u64(quotient(signed(a, 64), signed(b, 64))),
    OpR.DIVU: lambda a, b: u64(quotient(a, b)),
    OpR.REM: lambda a, b: u64(remainder(signed(a, 64), signed(b, 64))),
    OpR.REMU: remainder,
    OpR.MULW: lambda a, b: sext(a * b, 32),
    OpR.DIVW: lambda a, b: sext(quotient(signed(a, 32), signed(b, 32)), 32),
    OpR.DIVUW: lambda a, b: sext(quotient(a & LOW32, b & LOW32), 32),
    OpR.REMW: lambda a, b: sext(remainder(signed(a, 32), signed(b, 32)), 32),
    OpR.REMUW: lambda a, b: sext(remainder(a & LOW32, b & LOW32), 32),
}

# Each immediate operation is its register form with the immediate, sign-extended, as rs2.
IMMEDIATE: dict[OpI, OpR] = {
    OpI.ADDI: OpR.ADD,
    OpI.SLTI: OpR.SLT,
    OpI.SLTIU: OpR.SLTU,
    OpI.XORI: OpR.XOR,
    OpI.ORI: OpR.OR,
    OpI.ANDI: OpR.AND,
    OpI.ADDIW: OpR.ADDW,
}

# Each shift by an immediate amount is its register form with the amount as rs2.
SHIFTS: dict[OpShift, OpR] = {
    OpShift.SLLI: OpR.SLL,
    OpShift.SRLI: OpR.SRL,
    OpShift.SRAI: OpR.SRA,
    OpShift.SLLIW: OpR.SLLW,
    OpShift.SRLIW: OpR.SRLW,
    OpShift.SRAIW: OpR.SRAW,
}

# The upper-immediate operations on the 20-bit immediate and the instruction's address.
UPPER: dict[OpUpper, Callable[[int, int], int]] = {
    OpUpper.LUI: lambda imm, _: sext(imm << 12, 32),
    OpUpper.AUIPC: lambda imm, address: u64(address + sext(imm << 12, 32)),
}

# The mcause of each trapping instruction in M-mode (privileged spec, Table 14).
CAUSES: dict[OpBare, int] = {OpBare.ECALL: 11, OpBare.EBREAK: 3}


@dataclass(frozen=True, slots=True)
class Machine:
    """The 32 integer registers, x0 first, each in `[0, 2**64)`; x0 is 0."""

    regs: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Halted:
    """The run fell off the end of the program, leaving `machine`."""

    machine: Machine


@dataclass(frozen=True, slots=True)
class Trapped:
    """The instruction at `index` raised the exception `cause`, before changing `machine`."""

    cause: int
    index: int
    machine: Machine


@dataclass(frozen=True, slots=True)
class Unmodelled:
    """The instruction at `index` does what the evaluator does not know, for the reason `why`."""

    index: int
    why: str


@dataclass(frozen=True, slots=True)
class OutOfFuel:
    """The fuel ran out before the run ended."""


type Outcome = Halted | Trapped | Unmodelled | OutOfFuel


def arithmetic(instr: R | I | Shift | Upper, regs: list[int], address: int) -> int:
    """The value `instr` computes for rd from `regs`, at `address`."""
    match instr:
        case R():
            return ALU[instr.op](regs[instr.rs1], regs[instr.rs2])
        case I():
            return ALU[IMMEDIATE[instr.op]](regs[instr.rs1], u64(instr.imm))
        case Shift():
            return ALU[SHIFTS[instr.op]](regs[instr.rs1], u64(instr.shamt))
        case Upper():
            return UPPER[instr.op](instr.imm, address)
        case _:
            assert_never(instr)


def system(instr: Fence | Bare, index: int, regs: list[int]) -> int | Trapped:
    """The trap ecall or ebreak raises; the next index for the fences."""
    if isinstance(instr, Bare) and instr.op in CAUSES:
        return Trapped(CAUSES[instr.op], index, Machine(tuple(regs)))
    return index + 1


def step(instr: Instr, index: int, regs: list[int], base: int) -> int | Outcome:
    """Execute `instr` at `index` on `regs` in place: the next index, or how the run ends."""
    match instr:
        case R() | I() | Shift() | Upper():
            value = arithmetic(instr, regs, u64(base + 4 * index))
            if instr.rd != Reg.X0:
                regs[instr.rd] = value
            return index + 1
        case Branch() | Jal() | Jalr():
            return Unmodelled(index, f"{instr.op} is not followed")
        case Load() | Store():
            return Unmodelled(index, f"{instr.op} accesses memory, which is not modelled")
        case Fence() | Bare():
            return system(instr, index, regs)
        case _:
            assert_never(instr)


def run(program: Program, machine: Machine, base: int, fuel: int) -> Outcome:
    """Run `program` from its first instruction, at address `base`, for at most `fuel` steps.

    The registers change in a list local to the run; `machine` and the outcome are values.
    """
    code = tuple(item for item in program if not isinstance(item, Label))
    regs = list(machine.regs)
    index = 0
    for _ in range(fuel):
        if index == len(code):
            break
        after = step(code[index], index, regs, base)
        if not isinstance(after, int):
            return after
        index = after
    if index < len(code):
        return OutOfFuel()
    return Halted(Machine(tuple(regs)))
