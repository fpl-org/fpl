"""The RV64IM instructions as frozen values, one to one with the specification.

Spec: The RISC-V Instruction Set Manual, Volume I: Unprivileged Architecture, version 20250508;
section numbers are that release's. Each op enum's values are the mnemonics of the chapter 35
listing, lower-case; each class is one operand form. An out-of-subset mnemonic has no
constructor and a register cannot be out of range, both by construction. Immediates are plain
`int`: a value may hold an out-of-range immediate, because the checker must be able to say so.

Each class prints its own operands (`operands`) in the text `llvm-objdump -M no-aliases -M
numeric --no-print-imm-hex` prints: registers as `x<n>`, immediates in decimal.
"""

from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import override


class Reg(IntEnum):
    """The integer registers x0..x31 (2.1), always printed by number, never by ABI name."""

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
    X31 = 31

    @override
    def __str__(self) -> str:
        """The register as the canonical text prints it: `x10`, never `a0`."""
        return self.name.lower()


class OpR(StrEnum):
    """Register-register operations: 2.4.2, 4.2.2 (W forms), 12.1 and 12.2 (M)."""

    ADD = "add"
    SUB = "sub"
    SLL = "sll"
    SLT = "slt"
    SLTU = "sltu"
    XOR = "xor"
    SRL = "srl"
    SRA = "sra"
    OR = "or"
    AND = "and"
    ADDW = "addw"
    SUBW = "subw"
    SLLW = "sllw"
    SRLW = "srlw"
    SRAW = "sraw"
    MUL = "mul"
    MULH = "mulh"
    MULHSU = "mulhsu"
    MULHU = "mulhu"
    DIV = "div"
    DIVU = "divu"
    REM = "rem"
    REMU = "remu"
    MULW = "mulw"
    DIVW = "divw"
    DIVUW = "divuw"
    REMW = "remw"
    REMUW = "remuw"


class OpI(StrEnum):
    """Register-immediate operations with a 12-bit immediate: 2.4.1, 4.2.1."""

    ADDI = "addi"
    SLTI = "slti"
    SLTIU = "sltiu"
    XORI = "xori"
    ORI = "ori"
    ANDI = "andi"
    ADDIW = "addiw"


class OpUpper(StrEnum):
    """The upper-immediate operations (2.4.1; on RV64 the result is sign-extended, 4.2.1)."""

    LUI = "lui"
    AUIPC = "auipc"


class OpStore(StrEnum):
    """Stores of the low 1, 2, 4 or 8 bytes of rs2 (2.6, 4.3)."""

    SB = "sb"
    SH = "sh"
    SW = "sw"
    SD = "sd"


@dataclass(frozen=True, slots=True)
class R:
    """`op rd, rs1, rs2`."""

    op: OpR
    rd: Reg
    rs1: Reg
    rs2: Reg

    def operands(self) -> str:
        """`x1, x2, x3`."""
        return f"{self.rd!s}, {self.rs1!s}, {self.rs2!s}"


@dataclass(frozen=True, slots=True)
class I:  # noqa: E742 -- the spec's name for the format (2.2), as the design names the class
    """`op rd, rs1, imm`; the immediate is not range-checked here (the checker's IMM12)."""

    op: OpI
    rd: Reg
    rs1: Reg
    imm: int

    def operands(self) -> str:
        """`x1, x2, -1`."""
        return f"{self.rd!s}, {self.rs1!s}, {self.imm}"


@dataclass(frozen=True, slots=True)
class Upper:
    """`op rd, imm`, imm the unsigned 20-bit field as llvm-mc reads it (`lui x1, 1048575`)."""

    op: OpUpper
    rd: Reg
    imm: int

    def operands(self) -> str:
        """`x1, 1048575`."""
        return f"{self.rd!s}, {self.imm}"


@dataclass(frozen=True, slots=True)
class Store:
    """`op rs2, offset(rs1)`: store rs2 at rs1 + offset."""

    op: OpStore
    rs2: Reg
    rs1: Reg
    offset: int

    def operands(self) -> str:
        """`x6, 0(x5)`."""
        return f"{self.rs2!s}, {self.offset}({self.rs1!s})"


type Instr = R | I | Upper | Store
type Program = tuple[Instr, ...]
