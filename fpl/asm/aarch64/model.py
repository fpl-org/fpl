"""The A64 base integer instructions as frozen values, one class per C6.2 page family.

Spec: Arm Architecture Reference Manual for A-profile architecture, ARM DDI 0487, version M.d
(2026-09-29). Built so far: `MoveWide` (MOVN, MOVZ, MOVK: C6.2.284, C6.2.285, C6.2.283) and
`MulAdd` (MADD, MSUB: C6.2.275, C6.2.291).

The values are unchecked on purpose: an immediate may be out of range or a register may sit
in a slot that refuses it, so the model can hold every text the printer can be asked for; the
checker says what is wrong. Aliases (MOV, MUL, ...) are not constructs here: C1.4 makes them
the preferred disassembly of a base encoding, so they are `alias.py`'s, text only.
"""

from dataclasses import dataclass
from enum import IntEnum, StrEnum


class Width(IntEnum):
    """The operand size, the sf bit: 32-bit (w registers) or 64-bit (x registers)."""

    W32 = 32
    W64 = 64


class Reg(IntEnum):
    """A general-purpose register operand.

    X0..X30 are 0..30. Register number 31 is the stack pointer in some operand slots and the
    zero register in others (C6.1.3), so it is two members, SP = 31 and ZR = 32; each class's
    slots say which they admit, and the checker holds them to it.
    """

    X0 = 0
    X1 = 1
    X2 = 2
    X3 = 3
    X4 = 4
    X5 = 5
    X6 = 6
    X7 = 7
    X8 = 8
    X9 = 9
    X10 = 10
    X11 = 11
    X12 = 12
    X13 = 13
    X14 = 14
    X15 = 15
    X16 = 16
    X17 = 17
    X18 = 18
    X19 = 19
    X20 = 20
    X21 = 21
    X22 = 22
    X23 = 23
    X24 = 24
    X25 = 25
    X26 = 26
    X27 = 27
    X28 = 28
    X29 = 29
    X30 = 30
    SP = 31
    ZR = 32

    def name_at(self, width: Width) -> str:
        """The register's name at `width`: x3/w3, sp/wsp, xzr/wzr."""
        wide = width is Width.W64
        match self:
            case Reg.SP:
                return "sp" if wide else "wsp"
            case Reg.ZR:
                return "xzr" if wide else "wzr"
            case _:
                return f"{'x' if wide else 'w'}{self.value}"


class OpMoveWide(StrEnum):
    """The move-wide-immediate operations; each value is the base mnemonic."""

    MOVN = "movn"
    MOVZ = "movz"
    MOVK = "movk"


class OpMulAdd(StrEnum):
    """The multiply-accumulate operations; each value is the base mnemonic."""

    MADD = "madd"
    MSUB = "msub"


@dataclass(frozen=True, slots=True)
class MoveWide:
    """`op rd, #imm16, lsl #(16 * hw)`: C6.2.283-285. imm16 in [0, 65535] and hw below
    width / 16 are the checker's to demand, not the constructor's."""

    op: OpMoveWide
    width: Width
    rd: Reg
    imm16: int
    hw: int

    def operands(self) -> str:
        """The base form's operands; a zero shift is dropped, as llvm-objdump drops it."""
        shift = f", lsl #{16 * self.hw}" if self.hw else ""
        return f"{self.rd.name_at(self.width)}, #{self.imm16}{shift}"


@dataclass(frozen=True, slots=True)
class MulAdd:
    """`op rd, rn, rm, ra`: rd = ra + rn * rm (MADD) or ra - rn * rm (MSUB), C6.2.275, .291."""

    op: OpMulAdd
    width: Width
    rd: Reg
    rn: Reg
    rm: Reg
    ra: Reg

    def operands(self) -> str:
        """The base form's operands: four registers at the instruction's width."""
        regs = (self.rd, self.rn, self.rm, self.ra)
        return ", ".join(reg.name_at(self.width) for reg in regs)


@dataclass(frozen=True, slots=True)
class Label:
    """A definition when it is an item of a program; its name is `.L` + [A-Za-z0-9_]+, which
    the checker enforces (a `.L` label is assembler-local on both ELF and Mach-O)."""

    name: str


type Instr = MoveWide | MulAdd
type Item = Instr | Label
type Program = tuple[Item, ...]
