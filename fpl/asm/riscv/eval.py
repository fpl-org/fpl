"""The reference evaluator: what an RV64IM program does to the integer registers, purely.

`run(program, machine, base, fuel)` executes the program's instructions from the first, one
step each, and says how it ended: `Halted` on falling off the end, `Trapped` on ecall or ebreak,
`Unmodelled` at an instruction whose effect the evaluator does not know, `OutOfFuel` when
`fuel` steps did not reach an end. It never raises on a program the model can hold. The
machine is the integer registers and a window of memory, the bytes at the address x3 holds
when the run starts.

Register values are unsigned 64-bit ints, as QEMU reports them. `u64` wraps a Python int
into that range, `sext` sign-extends its low bits into it, and `signed` reads its low bits as
two's complement, the one reading the signed operations need. Semantics are tables keyed by
the op enums, one row per mnemonic. The W forms compute on the low 32 bits and sign-extend
the 32-bit result (4.2.1, 4.2.2), as do `lui` and `auipc` for their 32-bit immediate (4.2.1).
Division by zero and signed overflow follow Table 11 and never trap (12.2).

Contracts, checked by icontract on every call and by CrossHair in `make harden`: `sext` and
`alu`, the one door to the table, return register values given register values; `run` takes
a well-formed machine and never leaves anything but 0 in x0.

The pc is an instruction index: labels take no space, every instruction is 4 bytes. `base`
is the absolute address of instruction 0, which `auipc` adds and the links of `jal` and
`jalr` hold. A branch or `jal` goes to its label's first definition; a `jalr` goes to the
instruction at its target address, and a target that is no instruction of the program, or a
label never defined, ends the run as Unmodelled. Trapped and Unmodelled carry the instruction
index of the instruction they stopped at.

The system instructions follow the QEMU virt EEI in M-mode on one hart: ecall is cause 11
(environment call from M-mode), ebreak cause 3 (breakpoint), and fence and fence.tso order
nothing.

Loads and stores reach the window only. An access whose bytes all lie in it reads or writes
them little-endian, the low bytes of rs2 for a store, sign- or zero-extended by the mnemonic
for a load (2.6, 4.3). A misaligned access completes like an aligned one, as it does on QEMU
virt; 2.6 leaves that to the execution environment (hole `misaligned-access`). An access with
any byte outside the window is Unmodelled: real memory, or a fault, the evaluator does not know.
"""

import operator
from collections.abc import Callable
from dataclasses import dataclass
from typing import assert_never

import icontract

from fpl.asm.riscv.check import targets
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
    OpBranch,
    OpI,
    OpLoad,
    OpR,
    OpShift,
    OpStore,
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


def in_range(result: int) -> bool:
    """`result` is a register value: in `[0, 2**64)`."""
    return 0 <= result <= LOW64


def both_in_range(a: int, b: int) -> bool:
    """Both operands are register values."""
    return in_range(a) and in_range(b)


def a_width(bits: int) -> bool:
    """`bits` is a width with a sign bit."""
    return bits >= 1


def u64(value: int) -> int:
    """`value` modulo 2**64: the register value with the same low 64 bits."""
    return value & LOW64


def signed(value: int, bits: int) -> int:
    """The low `bits` bits of `value` read as a two's-complement number."""
    low = value & ((1 << bits) - 1)
    return low - (1 << bits) if low >> (bits - 1) else low


@icontract.require(a_width)
@icontract.ensure(in_range)
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

# The comparison each branch takes on (2.5.2).
BRANCHES: dict[OpBranch, Callable[[int, int], bool]] = {
    OpBranch.BEQ: operator.eq,
    OpBranch.BNE: operator.ne,
    OpBranch.BLT: lambda a, b: signed(a, 64) < signed(b, 64),
    OpBranch.BGE: lambda a, b: signed(a, 64) >= signed(b, 64),
    OpBranch.BLTU: operator.lt,
    OpBranch.BGEU: operator.ge,
}

# Each load's size in bytes, and whether it sign-extends what it reads (2.6, 4.3).
LOADS: dict[OpLoad, tuple[int, bool]] = {
    OpLoad.LB: (1, True),
    OpLoad.LH: (2, True),
    OpLoad.LW: (4, True),
    OpLoad.LBU: (1, False),
    OpLoad.LHU: (2, False),
    OpLoad.LWU: (4, False),
    OpLoad.LD: (8, True),
}

# Each store's size in bytes: how many low bytes of rs2 it writes (2.6, 4.3).
STORES: dict[OpStore, int] = {OpStore.SB: 1, OpStore.SH: 2, OpStore.SW: 4, OpStore.SD: 8}

# The mcause of each trapping instruction in M-mode (privileged spec, Table 14).
CAUSES: dict[OpBare, int] = {OpBare.ECALL: 11, OpBare.EBREAK: 3}


@dataclass(frozen=True, slots=True)
class Machine:
    """The 32 integer registers, x0 first, each in `[0, 2**64)`; x0 is 0; and the window.

    The window is the memory the program may load and store: its first byte is at the address
    x3 holds when a run starts.
    """

    regs: tuple[int, ...]
    window: bytes = b""


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


def well_formed(machine: Machine) -> bool:
    """32 registers, each in range, x0 zero."""
    regs = machine.regs
    return len(regs) == len(Reg) and regs[0] == 0 and all(map(in_range, regs))


def x0_zero(result: Outcome) -> bool:
    """The machine the run ends with, when it has one, holds 0 in x0."""
    return not isinstance(result, Halted | Trapped) or result.machine.regs[0] == 0


@icontract.require(both_in_range)
@icontract.ensure(in_range)
def alu(op: OpR, a: int, b: int) -> int:
    """The row of `op` on two register values: a register value."""
    return ALU[op](a, b)


@dataclass(frozen=True, slots=True)
class Code:
    """A program's instructions at address `base`, each label's instruction index by name, and
    the address of the window's first byte."""

    instrs: tuple[Instr, ...]
    labels: dict[str, int]
    base: int
    window: int

    def address(self, index: int) -> int:
        """The absolute address of the instruction at `index`."""
        return u64(self.base + 4 * index)


def write(regs: list[int], rd: Reg, value: int) -> None:
    """Set `rd` to `value`; a write to x0 is discarded (2.1)."""
    if rd != Reg.X0:
        regs[rd] = value


def arithmetic(instr: R | I | Shift | Upper, regs: list[int], address: int) -> int:
    """The value `instr` computes for rd from `regs`, at `address`."""
    match instr:
        case R():
            return alu(instr.op, regs[instr.rs1], regs[instr.rs2])
        case I():
            return alu(IMMEDIATE[instr.op], regs[instr.rs1], u64(instr.imm))
        case Shift():
            return alu(SHIFTS[instr.op], regs[instr.rs1], u64(instr.shamt))
        case Upper():
            return UPPER[instr.op](instr.imm, address)
        case _:
            assert_never(instr)


def system(instr: Fence | Bare, index: int, regs: list[int], window: bytearray) -> int | Trapped:
    """The trap ecall or ebreak raises; the next index for the fences."""
    if isinstance(instr, Bare) and instr.op in CAUSES:
        return Trapped(CAUSES[instr.op], index, Machine(tuple(regs), bytes(window)))
    return index + 1


def size(instr: Load | Store) -> int:
    """How many bytes `instr` accesses."""
    return LOADS[instr.op][0] if isinstance(instr, Load) else STORES[instr.op]


def access(
    instr: Load | Store, index: int, regs: list[int], window: bytearray, code: Code
) -> int | Unmodelled:
    """Load or store the window's bytes `instr` at `index` addresses: the next index."""
    width = size(instr)
    address = u64(regs[instr.rs1] + instr.offset)
    at = address - code.window
    if not 0 <= at <= len(window) - width:
        return Unmodelled(index, f"{instr.op} at {address:#x}: outside the window")
    if isinstance(instr, Load):
        value = int.from_bytes(window[at : at + width], "little")
        write(regs, instr.rd, sext(value, 8 * width) if LOADS[instr.op][1] else value)
    else:
        window[at : at + width] = regs[instr.rs2].to_bytes(8, "little")[:width]
    return index + 1


def resolve(code: Code, index: int, label: Label) -> int | Unmodelled:
    """The instruction index `label` names, for the jump at `index`."""
    target = code.labels.get(label.name)
    return Unmodelled(index, f"{label.name} is not defined") if target is None else target


def indirect(code: Code, index: int, address: int) -> int | Unmodelled:
    """The index of the instruction at `address`, for the `jalr` at `index`."""
    target, between = divmod(address - code.base, 4)
    if between or not 0 <= target < len(code.instrs):
        return Unmodelled(index, f"jalr to {address:#x}: no instruction of the program")
    return target


def control(
    instr: Branch | Jal | Jalr, index: int, regs: list[int], code: Code
) -> int | Unmodelled:
    """The index `instr` at `index` goes to, its link written once the target is known."""
    match instr:
        case Branch():
            if BRANCHES[instr.op](regs[instr.rs1], regs[instr.rs2]):
                return resolve(code, index, instr.target)
            return index + 1
        case Jal():
            target = resolve(code, index, instr.target)
        case Jalr():
            target = indirect(code, index, u64(regs[instr.rs1] + instr.offset) & ~1)
        case _:
            assert_never(instr)
    if isinstance(target, int):
        write(regs, instr.rd, code.address(index + 1))
    return target


def step(code: Code, index: int, regs: list[int], window: bytearray) -> int | Outcome:
    """Execute the instruction at `index` on `regs` and `window` in place: the next index, or
    the end."""
    instr = code.instrs[index]
    match instr:
        case R() | I() | Shift() | Upper():
            write(regs, instr.rd, arithmetic(instr, regs, code.address(index)))
            return index + 1
        case Branch() | Jal() | Jalr():
            return control(instr, index, regs, code)
        case Load() | Store():
            return access(instr, index, regs, window, code)
        case Fence() | Bare():
            return system(instr, index, regs, window)
        case _:
            assert_never(instr)


@icontract.require(well_formed)
@icontract.ensure(x0_zero)
def run(program: Program, machine: Machine, base: int, fuel: int) -> Outcome:
    """Run `program` from its first instruction, at address `base`, for at most `fuel` steps.

    The registers and the window change in a list and a bytearray local to the run; `machine`
    and the outcome are values.
    """
    instrs = tuple(item for item in program if not isinstance(item, Label))
    code = Code(instrs, targets(program), base, machine.regs[Reg.X3])
    regs = list(machine.regs)
    window = bytearray(machine.window)
    index = 0
    for _ in range(fuel):
        if index == len(instrs):
            break
        after = step(code, index, regs, window)
        if not isinstance(after, int):
            return after
        index = after
    if index < len(instrs):
        return OutOfFuel()
    return Halted(Machine(tuple(regs), bytes(window)))
