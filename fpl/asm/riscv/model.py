"""The RV64IM instructions as frozen values, one to one with the specification.

Spec: The RISC-V Instruction Set Manual, Volume I: Unprivileged Architecture, version 20250508;
section numbers are that release's. The mnemonics are the 66 of the chapter 35 listings (RV32I,
RV64I, RV32M, RV64M) without PAUSE, lower-case: each op enum's values, and the one fixed `op`
of each class that has no enum (`Jal`, `Jalr`, `Fence`). Each class is one operand form.

An out-of-subset mnemonic has no constructor and a register cannot be out of range, both by
construction. Immediates, shift amounts and offsets are plain `int`, and a label's name is any
`str`: a value may be out of range or ill-formed, because the checker must be able to say so
and the oracle must be able to refuse the same program. NOP is `I(OpI.ADDI, Reg.X0, Reg.X0, 0)`
(2.4.3), not a class; HINTs (2.9, 4.4) are ordinary members of these classes. Directives,
relocation operators, pseudo-instructions and aliases are not in the model.

The values hold no text: `fpl.asm.riscv.text` prints and parses them.
"""

from dataclasses import dataclass
from enum import IntEnum, IntFlag, StrEnum
from typing import ClassVar


class Reg(IntEnum):
    """The integer registers x0..x31 (2.1)."""

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


class Access(IntFlag):
    """The predecessor and successor sets of `fence` (2.7): device input and output, reads, writes.

    The values are the bits of the encoding's pred and succ fields.
    """

    I = 8  # noqa: E741 -- the spec's letter for device input
    O = 4  # noqa: E741 -- the spec's letter for device output
    R = 2
    W = 1


class OpR(StrEnum):
    """Register-register operations: 2.4.2, 4.2.2 (W forms), 12.1 and 12.2 (M)."""

    ADD = "add"  # 2.4.2
    SUB = "sub"  # 2.4.2
    SLL = "sll"  # 2.4.2
    SLT = "slt"  # 2.4.2
    SLTU = "sltu"  # 2.4.2
    XOR = "xor"  # 2.4.2
    SRL = "srl"  # 2.4.2
    SRA = "sra"  # 2.4.2
    OR = "or"  # 2.4.2
    AND = "and"  # 2.4.2
    ADDW = "addw"  # 4.2.2
    SUBW = "subw"  # 4.2.2
    SLLW = "sllw"  # 4.2.2
    SRLW = "srlw"  # 4.2.2
    SRAW = "sraw"  # 4.2.2
    MUL = "mul"  # 12.1
    MULH = "mulh"  # 12.1
    MULHSU = "mulhsu"  # 12.1
    MULHU = "mulhu"  # 12.1
    DIV = "div"  # 12.2
    DIVU = "divu"  # 12.2
    REM = "rem"  # 12.2
    REMU = "remu"  # 12.2
    MULW = "mulw"  # 12.1
    DIVW = "divw"  # 12.2
    DIVUW = "divuw"  # 12.2
    REMW = "remw"  # 12.2
    REMUW = "remuw"  # 12.2


class OpI(StrEnum):
    """Register-immediate operations with a 12-bit signed immediate: 2.4.1, 4.2.1."""

    ADDI = "addi"  # 2.4.1
    SLTI = "slti"  # 2.4.1
    SLTIU = "sltiu"  # 2.4.1
    XORI = "xori"  # 2.4.1
    ORI = "ori"  # 2.4.1
    ANDI = "andi"  # 2.4.1
    ADDIW = "addiw"  # 4.2.1


class OpShift(StrEnum):
    """Shifts by an immediate amount: 6 bits wide on RV64, 5 bits for the W forms (4.2.1).

    SLLI, SRLI and SRAI are the RV64I rows of the listing, which redefine the RV32I rows with
    a 6-bit shamt, so their section is 4.2.1 rather than 2.4.1.
    """

    SLLI = "slli"  # 4.2.1
    SRLI = "srli"  # 4.2.1
    SRAI = "srai"  # 4.2.1
    SLLIW = "slliw"  # 4.2.1
    SRLIW = "srliw"  # 4.2.1
    SRAIW = "sraiw"  # 4.2.1


class OpUpper(StrEnum):
    """The upper-immediate operations (2.4.1; on RV64 the result is sign-extended, 4.2.1)."""

    LUI = "lui"  # 2.4.1
    AUIPC = "auipc"  # 2.4.1


class OpLoad(StrEnum):
    """Loads of 1, 2, 4 or 8 bytes, sign- or zero-extended to 64 bits (2.6, 4.3)."""

    LB = "lb"  # 2.6
    LH = "lh"  # 2.6
    LW = "lw"  # 2.6
    LBU = "lbu"  # 2.6
    LHU = "lhu"  # 2.6
    LWU = "lwu"  # 4.3
    LD = "ld"  # 4.3


class OpStore(StrEnum):
    """Stores of the low 1, 2, 4 or 8 bytes of rs2 (2.6, 4.3)."""

    SB = "sb"  # 2.6
    SH = "sh"  # 2.6
    SW = "sw"  # 2.6
    SD = "sd"  # 4.3


class OpBranch(StrEnum):
    """Conditional branches comparing rs1 with rs2, signed or unsigned (2.5.2)."""

    BEQ = "beq"  # 2.5.2
    BNE = "bne"  # 2.5.2
    BLT = "blt"  # 2.5.2
    BGE = "bge"  # 2.5.2
    BLTU = "bltu"  # 2.5.2
    BGEU = "bgeu"  # 2.5.2


class OpBare(StrEnum):
    """The operand-free instructions: 2.7 (FENCE.TSO), 2.8 (ECALL, EBREAK)."""

    FENCE_TSO = "fence.tso"  # 2.7
    ECALL = "ecall"  # 2.8
    EBREAK = "ebreak"  # 2.8


@dataclass(frozen=True, slots=True)
class Label:
    """A position in the program: a definition as an item, a reference inside `Branch` or `Jal`.

    The name is not checked here; the checker requires `.L` and then `[A-Za-z0-9_]+`.
    """

    name: str


@dataclass(frozen=True, slots=True)
class R:
    """`op rd, rs1, rs2`: the R-type format (2.2)."""

    op: OpR
    rd: Reg
    rs1: Reg
    rs2: Reg


@dataclass(frozen=True, slots=True)
class I:  # noqa: E742 -- the spec's name for the format (2.2), as the design names the class
    """`op rd, rs1, imm`: the I-type format; the immediate is the checker's IMM12."""

    op: OpI
    rd: Reg
    rs1: Reg
    imm: int


@dataclass(frozen=True, slots=True)
class Shift:
    """`op rd, rs1, shamt`: an I-type shift; the amount is the checker's SHAMT6 or SHAMT5."""

    op: OpShift
    rd: Reg
    rs1: Reg
    shamt: int


@dataclass(frozen=True, slots=True)
class Upper:
    """`op rd, imm`, imm the unsigned 20-bit field as llvm-mc reads it (`lui x1, 1048575`)."""

    op: OpUpper
    rd: Reg
    imm: int


@dataclass(frozen=True, slots=True)
class Load:
    """`op rd, offset(rs1)`: load from rs1 + offset into rd."""

    op: OpLoad
    rd: Reg
    rs1: Reg
    offset: int


@dataclass(frozen=True, slots=True)
class Store:
    """`op rs2, offset(rs1)`: store rs2 at rs1 + offset."""

    op: OpStore
    rs2: Reg
    rs1: Reg
    offset: int


@dataclass(frozen=True, slots=True)
class Branch:
    """`op rs1, rs2, target`: branch to the label when the comparison holds (2.5.2)."""

    op: OpBranch
    rs1: Reg
    rs2: Reg
    target: Label


@dataclass(frozen=True, slots=True)
class Jal:
    """`jal rd, target`: jump to the label, the return address in rd (2.5.1)."""

    op: ClassVar[str] = "jal"  # 2.5.1
    rd: Reg
    target: Label


@dataclass(frozen=True, slots=True)
class Jalr:
    """`jalr rd, offset(rs1)`: jump to (rs1 + offset) with bit 0 cleared, return address in rd."""

    op: ClassVar[str] = "jalr"  # 2.5.1
    rd: Reg
    rs1: Reg
    offset: int


@dataclass(frozen=True, slots=True)
class Fence:
    """`fence pred, succ`: order the predecessor set before the successor set (2.7)."""

    op: ClassVar[str] = "fence"  # 2.7
    pred: Access
    succ: Access


@dataclass(frozen=True, slots=True)
class Bare:
    """`op`, no operands."""

    op: OpBare


type Instr = R | I | Shift | Upper | Load | Store | Branch | Jal | Jalr | Fence | Bare
type Item = Instr | Label
type Program = tuple[Item, ...]
"""The text section of one translation unit, in order."""
