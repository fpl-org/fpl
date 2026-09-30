"""The A64 base integer instructions as frozen values, one class per C6.2 page family.

Spec: Arm Architecture Reference Manual for A-profile architecture, ARM DDI 0487, version M.d
(2026-09-29), C6.2 "Alphabetical list of A64 base instructions": 105 pages, 82 mnemonics. Each
class docstring names its pages; a page with several addressing modes (LDR (immediate):
unsigned offset, pre-index, post-index) is one class and one op with an addressing sum type.

The values are unchecked on purpose: an immediate may be out of range or a register may sit
in a slot that refuses it, so the model can hold every text the printer can be asked for; the
checker says what is wrong. Aliases (MOV, CMP, LSL, ...) are not constructs here: C1.4 makes
them the preferred disassembly of a base encoding, so they are `alias.py`'s, text only.

`operands()` on each class is its base form's operand text as llvm-objdump prints it: default
shifts (`lsl #0`), default extends and zero unsigned offsets dropped.
"""

from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import ClassVar, assert_never


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


class Cond(IntEnum):
    """A condition code, C1.2.4, by its encoding; `hs` and `lo` are llvm-objdump's names
    for cs and cc."""

    EQ = 0
    NE = 1
    HS = 2
    LO = 3
    MI = 4
    PL = 5
    VS = 6
    VC = 7
    HI = 8
    LS = 9
    GE = 10
    LT = 11
    GT = 12
    LE = 13
    AL = 14
    NV = 15

    @property
    def text(self) -> str:
        """The condition's name as printed: eq, ne, hs, ..."""
        return self.name.lower()

    def inverse(self) -> "Cond":
        """The condition with its low bit flipped (C1.2.4 pairs each with its negation)."""
        return Cond(self ^ 1)


class Shift(StrEnum):
    """A register shift (C6.2.6 and the other shifted-register pages)."""

    LSL = "lsl"
    LSR = "lsr"
    ASR = "asr"
    ROR = "ror"  # logical (shifted register) only; the checker refuses it in add and sub


class Extend(StrEnum):
    """A register extend (C6.2.4 and the extended-register pages; four of them in memory)."""

    UXTB = "uxtb"
    UXTH = "uxth"
    UXTW = "uxtw"
    UXTX = "uxtx"
    SXTB = "sxtb"
    SXTH = "sxth"
    SXTW = "sxtw"
    SXTX = "sxtx"


def names(width: Width, *regs: Reg) -> str:
    """The registers' names at `width`, comma-separated."""
    return ", ".join(reg.name_at(width) for reg in regs)


def shifted(shift: Shift, amount: int) -> str:
    """`, shift #amount`, or nothing for the default `lsl #0`."""
    return "" if shift is Shift.LSL and amount == 0 else f", {shift.value} #{amount}"


class OpAddSub(StrEnum):
    """Add and subtract, flag-setting or not; each value is the base mnemonic."""

    ADD = "add"  # C6.2.5 (immediate), C6.2.6 (shifted register), C6.2.4 (extended register)
    ADDS = "adds"  # C6.2.10 (immediate), C6.2.11 (shifted register), C6.2.9 (extended register)
    SUB = "sub"  # C6.2.457 (immediate), C6.2.458 (shifted register), C6.2.456 (extended)
    SUBS = "subs"  # C6.2.464 (immediate), C6.2.465 (shifted register), C6.2.463 (extended)


class OpAddSubCarry(StrEnum):
    """Add and subtract with carry."""

    ADC = "adc"  # C6.2.2
    ADCS = "adcs"  # C6.2.3
    SBC = "sbc"  # C6.2.352
    SBCS = "sbcs"  # C6.2.353


class OpLogicalImm(StrEnum):
    """The logical operations with a bitmask immediate."""

    AND = "and"  # C6.2.14 AND (immediate)
    ORR = "orr"  # C6.2.301 ORR (immediate)
    EOR = "eor"  # C6.2.155 EOR (immediate)
    ANDS = "ands"  # C6.2.16 ANDS (immediate)


class OpLogical(StrEnum):
    """The logical operations on a shifted register."""

    AND = "and"  # C6.2.15 AND (shifted register)
    BIC = "bic"  # C6.2.41 BIC (shifted register)
    ORR = "orr"  # C6.2.302 ORR (shifted register)
    ORN = "orn"  # C6.2.300 ORN (shifted register)
    EOR = "eor"  # C6.2.156 EOR (shifted register)
    EON = "eon"  # C6.2.154 EON (shifted register)
    ANDS = "ands"  # C6.2.17 ANDS (shifted register)
    BICS = "bics"  # C6.2.42 BICS (shifted register)


class OpMoveWide(StrEnum):
    """The move-wide-immediate operations."""

    MOVN = "movn"  # C6.2.284
    MOVZ = "movz"  # C6.2.285
    MOVK = "movk"  # C6.2.283


class OpBitfield(StrEnum):
    """The bitfield moves."""

    SBFM = "sbfm"  # C6.2.355
    BFM = "bfm"  # C6.2.39
    UBFM = "ubfm"  # C6.2.487


class OpDataProc2(StrEnum):
    """The two-source data-processing operations."""

    LSLV = "lslv"  # C6.2.271
    LSRV = "lsrv"  # C6.2.274
    ASRV = "asrv"  # C6.2.21
    RORV = "rorv"  # C6.2.349
    SDIV = "sdiv"  # C6.2.357 SDIV (quotient)
    UDIV = "udiv"  # C6.2.490 UDIV (quotient)


class OpDataProc1(StrEnum):
    """The one-source data-processing operations."""

    RBIT = "rbit"  # C6.2.321
    REV16 = "rev16"  # C6.2.343
    REV = "rev"  # C6.2.342
    REV32 = "rev32"  # C6.2.344, 64-bit only (the checker's)
    CLZ = "clz"  # C6.2.91
    CLS = "cls"  # C6.2.90


class OpMulAdd(StrEnum):
    """The multiply-accumulate operations."""

    MADD = "madd"  # C6.2.275
    MSUB = "msub"  # C6.2.291


class OpMulLong(StrEnum):
    """The widening multiply-accumulate operations: X <- W * W +/- X."""

    SMADDL = "smaddl"  # C6.2.369
    SMSUBL = "smsubl"  # C6.2.378
    UMADDL = "umaddl"  # C6.2.491
    UMSUBL = "umsubl"  # C6.2.497


class OpMulHigh(StrEnum):
    """The high-half multiplies: X <- (X * X) >> 64."""

    SMULH = "smulh"  # C6.2.379
    UMULH = "umulh"  # C6.2.498


class OpCondSelect(StrEnum):
    """The conditional selects."""

    CSEL = "csel"  # C6.2.138
    CSINC = "csinc"  # C6.2.141
    CSINV = "csinv"  # C6.2.142
    CSNEG = "csneg"  # C6.2.143


class OpCondCompare(StrEnum):
    """The conditional compares, register or immediate."""

    CCMN = "ccmn"  # C6.2.80 (register), C6.2.79 (immediate)
    CCMP = "ccmp"  # C6.2.82 (register), C6.2.81 (immediate)


class OpBranch(StrEnum):
    """The unconditional immediate branches."""

    B = "b"  # C6.2.35
    BL = "bl"  # C6.2.43


class OpCompareBranch(StrEnum):
    """Compare with zero and branch."""

    CBZ = "cbz"  # C6.2.78
    CBNZ = "cbnz"  # C6.2.77


class OpTestBranch(StrEnum):
    """Test a bit and branch."""

    TBZ = "tbz"  # C6.2.479
    TBNZ = "tbnz"  # C6.2.478


class OpBranchReg(StrEnum):
    """The branches to a register."""

    BR = "br"  # C6.2.46
    BLR = "blr"  # C6.2.44
    RET = "ret"  # C6.2.338


SIZES = {"b": 1, "h": 2, "w": 4}  # access size by the mnemonic's last letter; else the width's


class Access(StrEnum):
    """A single-register load or store. A value is the base mnemonic, suffixed `_w` or `_x`
    where one page has both widths; the transfer width and the access size follow from it."""

    @property
    def mnemonic(self) -> str:
        """The base mnemonic: the value without its width suffix."""
        return self.value.partition("_")[0]

    @property
    def width(self) -> Width:
        """The transfer register's width: x for the `_x` forms and the sign-extending word
        loads, w otherwise."""
        wide = self.value.endswith(("_x", "sw"))
        return Width.W64 if wide else Width.W32

    @property
    def size(self) -> int:
        """The bytes accessed: 1, 2 or 4 by the mnemonic's last letter, else the width's."""
        return SIZES.get(self.mnemonic[-1], self.width // 8)


class OpLoadStore(Access):
    """The loads and stores with an immediate or register offset (two pages each)."""

    STRB = "strb"  # C6.2.417 STRB (immediate), C6.2.418 STRB (register)
    LDRB = "ldrb"  # C6.2.220 LDRB (immediate), C6.2.221 LDRB (register)
    LDRSB_W = "ldrsb_w"  # C6.2.224 LDRSB (immediate), C6.2.225 LDRSB (register)
    LDRSB_X = "ldrsb_x"  # C6.2.224 LDRSB (immediate), C6.2.225 LDRSB (register)
    STRH = "strh"  # C6.2.419 STRH (immediate), C6.2.420 STRH (register)
    LDRH = "ldrh"  # C6.2.222 LDRH (immediate), C6.2.223 LDRH (register)
    LDRSH_W = "ldrsh_w"  # C6.2.226 LDRSH (immediate), C6.2.227 LDRSH (register)
    LDRSH_X = "ldrsh_x"  # C6.2.226 LDRSH (immediate), C6.2.227 LDRSH (register)
    STR_W = "str_w"  # C6.2.415 STR (immediate), C6.2.416 STR (register)
    STR_X = "str_x"  # C6.2.415 STR (immediate), C6.2.416 STR (register)
    LDR_W = "ldr_w"  # C6.2.216 LDR (immediate), C6.2.218 LDR (register)
    LDR_X = "ldr_x"  # C6.2.216 LDR (immediate), C6.2.218 LDR (register)
    LDRSW = "ldrsw"  # C6.2.228 LDRSW (immediate), C6.2.230 LDRSW (register)


class OpLoadStoreUnscaled(Access):
    """The loads and stores with an unscaled signed 9-bit offset."""

    STURB = "sturb"  # C6.2.447
    STURH = "sturh"  # C6.2.448
    STUR_W = "stur_w"  # C6.2.446
    STUR_X = "stur_x"  # C6.2.446
    LDURB = "ldurb"  # C6.2.260
    LDURH = "ldurh"  # C6.2.261
    LDURSB_W = "ldursb_w"  # C6.2.262
    LDURSB_X = "ldursb_x"  # C6.2.262
    LDURSH_W = "ldursh_w"  # C6.2.263
    LDURSH_X = "ldursh_x"  # C6.2.263
    LDUR_W = "ldur_w"  # C6.2.259
    LDUR_X = "ldur_x"  # C6.2.259
    LDURSW = "ldursw"  # C6.2.264


class OpPair(StrEnum):
    """The register-pair loads and stores."""

    STP = "stp"  # C6.2.414
    LDP = "ldp"  # C6.2.214
    LDPSW = "ldpsw"  # C6.2.215, 64-bit only (the checker's)


class Mode(StrEnum):
    """An immediate addressing mode: unsigned (or pair) offset, pre-index, post-index."""

    OFFSET = "offset"
    PRE = "pre"
    POST = "post"


def address(rn: Reg, imm: int, mode: Mode) -> str:
    """`[rn, #imm]` (`[rn]` for a zero offset), `[rn, #imm]!` or `[rn], #imm`."""
    base = rn.name_at(Width.W64)
    match mode:
        case Mode.OFFSET:
            return f"[{base}, #{imm}]" if imm else f"[{base}]"
        case Mode.PRE:
            return f"[{base}, #{imm}]!"
        case Mode.POST:
            return f"[{base}], #{imm}"
        case _:
            assert_never(mode)


@dataclass(frozen=True, slots=True)
class Label:
    """A definition when it is an item of a program, a reference inside a branch or `adr`;
    its name is `.L` + [A-Za-z0-9_]+, which the checker enforces (a `.L` label is
    assembler-local on both ELF and Mach-O)."""

    name: str


@dataclass(frozen=True, slots=True)
class AddSubImm:
    """`op rd, rn, #imm{, lsl #12}`: ADD, ADDS, SUB, SUBS (immediate), C6.2.5, .10, .457,
    .464. rd admits sp (add, sub) or zr (adds, subs), rn sp; imm in [0, 4095]."""

    op: OpAddSub
    width: Width
    rd: Reg
    rn: Reg
    imm: int
    lsl12: bool

    def operands(self) -> str:
        """rd, rn, the immediate and its shift when set."""
        shift = ", lsl #12" if self.lsl12 else ""
        return f"{names(self.width, self.rd, self.rn)}, #{self.imm}{shift}"


@dataclass(frozen=True, slots=True)
class AddSubShifted:
    """`op rd, rn, rm{, shift #amount}`: ADD, ADDS, SUB, SUBS (shifted register), C6.2.6,
    .11, .458, .465. Registers admit zr; shift lsl, lsr or asr; amount below the width."""

    op: OpAddSub
    width: Width
    rd: Reg
    rn: Reg
    rm: Reg
    shift: Shift
    amount: int

    def operands(self) -> str:
        """Three registers and the shift, dropped when it is `lsl #0`."""
        regs = names(self.width, self.rd, self.rn, self.rm)
        return regs + shifted(self.shift, self.amount)


@dataclass(frozen=True, slots=True)
class AddSubExtended:
    """`op rd, rn, rm, extend{ #amount}`: ADD, ADDS, SUB, SUBS (extended register), C6.2.4,
    .9, .456, .463. rd admits sp (add, sub) or zr, rn sp, rm zr; amount in [0, 4]."""

    op: OpAddSub
    width: Width
    rd: Reg
    rn: Reg
    rm: Reg
    extend: Extend
    amount: int

    def extension(self) -> str:
        """`, extend #amount`, the amount dropped when zero; next to sp the width's own
        extend (uxtx, or uxtw at 32 bits) prints as `lsl`, and `lsl #0` not at all."""
        own = Extend.UXTX if self.width is Width.W64 else Extend.UXTW
        if self.extend is own and Reg.SP in (self.rd, self.rn):
            return f", lsl #{self.amount}" if self.amount else ""
        return f", {self.extend.value}" + (f" #{self.amount}" if self.amount else "")

    def rm_name(self) -> str:
        """rm is an x register only for uxtx and sxtx in a 64-bit instruction."""
        wide = self.width is Width.W64 and self.extend in (Extend.UXTX, Extend.SXTX)
        return self.rm.name_at(Width.W64 if wide else Width.W32)

    def operands(self) -> str:
        """rd, rn, rm at its extend's width, and the extend."""
        return f"{names(self.width, self.rd, self.rn)}, {self.rm_name()}{self.extension()}"


@dataclass(frozen=True, slots=True)
class AddSubCarry:
    """`op rd, rn, rm`: ADC, ADCS, SBC, SBCS, C6.2.2, .3, .352, .353. Registers admit zr."""

    op: OpAddSubCarry
    width: Width
    rd: Reg
    rn: Reg
    rm: Reg

    def operands(self) -> str:
        """Three registers at the width."""
        return names(self.width, self.rd, self.rn, self.rm)


@dataclass(frozen=True, slots=True)
class LogicalImm:
    """`op rd, rn, #imm`: AND, ORR, EOR, ANDS (immediate), C6.2.14, .301, .155, .16. imm is
    the value; its encodability as N:immr:imms (DecodeBitMasks) is the checker's question."""

    op: OpLogicalImm
    width: Width
    rd: Reg
    rn: Reg
    imm: int

    def operands(self) -> str:
        """rd, rn and the value in hex, as llvm-objdump prints logical immediates."""
        return f"{names(self.width, self.rd, self.rn)}, #{hex(self.imm)}"


@dataclass(frozen=True, slots=True)
class LogicalShifted:
    """`op rd, rn, rm{, shift #amount}`: AND, BIC, ORR, ORN, EOR, EON, ANDS, BICS (shifted
    register), C6.2.15, .41, .302, .300, .156, .154, .17, .42. Any shift, ror included."""

    op: OpLogical
    width: Width
    rd: Reg
    rn: Reg
    rm: Reg
    shift: Shift
    amount: int

    def operands(self) -> str:
        """Three registers and the shift, dropped when it is `lsl #0`."""
        return names(self.width, self.rd, self.rn, self.rm) + shifted(self.shift, self.amount)


@dataclass(frozen=True, slots=True)
class MoveWide:
    """`op rd, #imm16, lsl #(16 * hw)`: MOVN, MOVZ, MOVK, C6.2.284, .285, .283. imm16 in
    [0, 65535] and hw below width / 16 are the checker's to demand, not the constructor's."""

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
class Bitfield:
    """`op rd, rn, #immr, #imms`: SBFM, BFM, UBFM, C6.2.355, .39, .487; immr and imms below
    the width (N is the sf bit, not a field)."""

    op: OpBitfield
    width: Width
    rd: Reg
    rn: Reg
    immr: int
    imms: int

    def operands(self) -> str:
        """rd, rn, immr, imms."""
        return f"{names(self.width, self.rd, self.rn)}, #{self.immr}, #{self.imms}"


@dataclass(frozen=True, slots=True)
class Extract:
    """`extr rd, rn, rm, #lsb`: EXTR, C6.2.160; lsb below the width."""

    MNEMONIC: ClassVar[str] = "extr"
    width: Width
    rd: Reg
    rn: Reg
    rm: Reg
    lsb: int

    def operands(self) -> str:
        """Three registers and the lsb."""
        return f"{names(self.width, self.rd, self.rn, self.rm)}, #{self.lsb}"


@dataclass(frozen=True, slots=True)
class Adr:
    """`adr rd, label`: ADR, C6.2.12; the label within +/-1 MiB."""

    MNEMONIC: ClassVar[str] = "adr"
    rd: Reg
    target: Label

    def operands(self) -> str:
        """The x register and the label's name."""
        return f"{self.rd.name_at(Width.W64)}, {self.target.name}"


@dataclass(frozen=True, slots=True)
class DataProc2:
    """`op rd, rn, rm`: LSLV, LSRV, ASRV, RORV, SDIV, UDIV, C6.2.271, .274, .21, .349, .357,
    .490."""

    op: OpDataProc2
    width: Width
    rd: Reg
    rn: Reg
    rm: Reg

    def operands(self) -> str:
        """Three registers at the width."""
        return names(self.width, self.rd, self.rn, self.rm)


@dataclass(frozen=True, slots=True)
class DataProc1:
    """`op rd, rn`: RBIT, REV16, REV, REV32, CLZ, CLS, C6.2.321, .343, .342, .344, .91, .90."""

    op: OpDataProc1
    width: Width
    rd: Reg
    rn: Reg

    def operands(self) -> str:
        """Two registers at the width."""
        return names(self.width, self.rd, self.rn)


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
        return names(self.width, self.rd, self.rn, self.rm, self.ra)


@dataclass(frozen=True, slots=True)
class MulLong:
    """`op xd, wn, wm, xa`: SMADDL, SMSUBL, UMADDL, UMSUBL, C6.2.369, .378, .491, .497; the
    widths are fixed by the encoding, so they are not fields."""

    op: OpMulLong
    rd: Reg
    rn: Reg
    rm: Reg
    ra: Reg

    def operands(self) -> str:
        """x, w, w, x."""
        wide = self.rd.name_at(Width.W64), self.ra.name_at(Width.W64)
        return f"{wide[0]}, {names(Width.W32, self.rn, self.rm)}, {wide[1]}"


@dataclass(frozen=True, slots=True)
class MulHigh:
    """`op xd, xn, xm`: SMULH, UMULH, C6.2.379, .498; always 64-bit."""

    op: OpMulHigh
    rd: Reg
    rn: Reg
    rm: Reg

    def operands(self) -> str:
        """Three x registers."""
        return names(Width.W64, self.rd, self.rn, self.rm)


@dataclass(frozen=True, slots=True)
class CondSelect:
    """`op rd, rn, rm, cond`: CSEL, CSINC, CSINV, CSNEG, C6.2.138, .141, .142, .143."""

    op: OpCondSelect
    width: Width
    rd: Reg
    rn: Reg
    rm: Reg
    cond: Cond

    def operands(self) -> str:
        """Three registers and the condition."""
        return f"{names(self.width, self.rd, self.rn, self.rm)}, {self.cond.text}"


@dataclass(frozen=True, slots=True)
class CondCompareReg:
    """`op rn, rm, #nzcv, cond`: CCMN, CCMP (register), C6.2.80, .82; nzcv in [0, 15]."""

    op: OpCondCompare
    width: Width
    rn: Reg
    rm: Reg
    nzcv: int
    cond: Cond

    def operands(self) -> str:
        """Two registers, the flags to set when cond fails, the condition."""
        return f"{names(self.width, self.rn, self.rm)}, #{self.nzcv}, {self.cond.text}"


@dataclass(frozen=True, slots=True)
class CondCompareImm:
    """`op rn, #imm5, #nzcv, cond`: CCMN, CCMP (immediate), C6.2.79, .81; imm5 in [0, 31]."""

    op: OpCondCompare
    width: Width
    rn: Reg
    imm5: int
    nzcv: int
    cond: Cond

    def operands(self) -> str:
        """The register, the immediate, the flags, the condition."""
        rn = self.rn.name_at(self.width)
        return f"{rn}, #{self.imm5}, #{self.nzcv}, {self.cond.text}"


@dataclass(frozen=True, slots=True)
class Branch:
    """`op label`: B, BL, C6.2.35, .43; the label within +/-128 MiB."""

    op: OpBranch
    target: Label

    def operands(self) -> str:
        """The label's name."""
        return self.target.name


@dataclass(frozen=True, slots=True)
class BranchCond:
    """`b.cond label`: B.cond, C6.2.34; the label within +/-1 MiB."""

    MNEMONIC: ClassVar[str] = "b."
    cond: Cond
    target: Label

    def operands(self) -> str:
        """The label's name; the condition is part of the mnemonic."""
        return self.target.name


@dataclass(frozen=True, slots=True)
class CompareBranch:
    """`op rt, label`: CBZ, CBNZ, C6.2.78, .77; the label within +/-1 MiB."""

    op: OpCompareBranch
    width: Width
    rt: Reg
    target: Label

    def operands(self) -> str:
        """The register at the width and the label's name."""
        return f"{self.rt.name_at(self.width)}, {self.target.name}"


@dataclass(frozen=True, slots=True)
class TestBranch:
    """`op rt, #bit, label`: TBZ, TBNZ, C6.2.479, .478; bit in [0, 63] (its top bit, b5, is
    the width: rt is printed w below 32), the label within +/-32 KiB."""

    op: OpTestBranch
    rt: Reg
    bit: int
    target: Label

    def operands(self) -> str:
        """The register at the bit's width, the bit, the label's name."""
        width = Width.W32 if 0 <= self.bit < 32 else Width.W64
        return f"{self.rt.name_at(width)}, #{self.bit}, {self.target.name}"


@dataclass(frozen=True, slots=True)
class BranchReg:
    """`op rn`: BR, BLR, RET, C6.2.46, .44, .338; `ret` with x30 prints no operand."""

    op: OpBranchReg
    rn: Reg

    def operands(self) -> str:
        """The x register, or nothing for RET's default x30."""
        default = self.op is OpBranchReg.RET and self.rn is Reg.X30
        return "" if default else self.rn.name_at(Width.W64)


@dataclass(frozen=True, slots=True)
class Nop:
    """`nop`: NOP, C6.2.299."""

    MNEMONIC: ClassVar[str] = "nop"

    def operands(self) -> str:
        """No operands."""
        return ""


@dataclass(frozen=True, slots=True)
class Offset:
    """Unsigned offset, `[rn, #imm]`: imm in bytes, a multiple of the access size below
    4096 of them (the checker's)."""

    rn: Reg
    imm: int

    def text(self, size: int) -> str:  # noqa: ARG002 -- the size scales only RegOffset
        """`[rn, #imm]`, or `[rn]` for zero."""
        return address(self.rn, self.imm, Mode.OFFSET)


@dataclass(frozen=True, slots=True)
class PreIndex:
    """Pre-index, `[rn, #imm]!`: imm a signed 9-bit byte offset, written back first."""

    rn: Reg
    imm: int

    def text(self, size: int) -> str:  # noqa: ARG002 -- the size scales only RegOffset
        """`[rn, #imm]!`, zero included."""
        return address(self.rn, self.imm, Mode.PRE)


@dataclass(frozen=True, slots=True)
class PostIndex:
    """Post-index, `[rn], #imm`: imm a signed 9-bit byte offset, written back after."""

    rn: Reg
    imm: int

    def text(self, size: int) -> str:  # noqa: ARG002 -- the size scales only RegOffset
        """`[rn], #imm`, zero included."""
        return address(self.rn, self.imm, Mode.POST)


@dataclass(frozen=True, slots=True)
class RegOffset:
    """Register offset, `[rn, rm{, option{ #amount}}]`: option UXTW, UXTX (printed `lsl`),
    SXTW or SXTX; `s` is the S bit, and the amount is log2(size) when set, 0 when clear. An
    amount alone would lose an encoding at byte size, where both S values mean 0."""

    rn: Reg
    rm: Reg
    option: Extend
    s: bool

    def text(self, size: int) -> str:
        """`[rn, rm]` for uxtx without S; otherwise the option, and the amount when S."""
        wide = self.option not in (Extend.UXTW, Extend.SXTW)
        regs = f"{self.rn.name_at(Width.W64)}, {self.rm.name_at(Width.W64 if wide else Width.W32)}"
        if self.option is Extend.UXTX and not self.s:
            return f"[{regs}]"
        option = "lsl" if self.option is Extend.UXTX else self.option.value
        amount = f" #{size.bit_length() - 1}" if self.s else ""
        return f"[{regs}, {option}{amount}]"


type Addr = Offset | PreIndex | PostIndex | RegOffset


@dataclass(frozen=True, slots=True)
class LoadStore:
    """`op rt, addr`: the single-register loads and stores with an immediate (unsigned offset,
    pre- or post-index) or register offset; two C6.2 pages per mnemonic (OpLoadStore)."""

    op: OpLoadStore
    rt: Reg
    addr: Addr

    def operands(self) -> str:
        """rt at the op's width and the address."""
        return f"{self.rt.name_at(self.op.width)}, {self.addr.text(self.op.size)}"


@dataclass(frozen=True, slots=True)
class LoadStoreUnscaled:
    """`op rt, [rn, #simm9]`: STUR*, LDUR*, C6.2.446-448, .259-.264; simm9 in [-256, 255]."""

    op: OpLoadStoreUnscaled
    rt: Reg
    rn: Reg
    simm9: int

    def operands(self) -> str:
        """rt at the op's width and `[rn, #simm9]`, `[rn]` for zero."""
        return f"{self.rt.name_at(self.op.width)}, {address(self.rn, self.simm9, Mode.OFFSET)}"


@dataclass(frozen=True, slots=True)
class Pair:
    """`op rt, rt2, addr`: STP, LDP, LDPSW, C6.2.414, .214, .215; imm a multiple of the
    access size in [-64, 63] of them, in one of three modes."""

    op: OpPair
    width: Width
    rt: Reg
    rt2: Reg
    rn: Reg
    imm: int
    mode: Mode

    def operands(self) -> str:
        """rt, rt2 and the address in the mode."""
        return f"{names(self.width, self.rt, self.rt2)}, {address(self.rn, self.imm, self.mode)}"


type Instr = (
    AddSubImm
    | AddSubShifted
    | AddSubExtended
    | AddSubCarry
    | LogicalImm
    | LogicalShifted
    | MoveWide
    | Bitfield
    | Extract
    | Adr
    | DataProc2
    | DataProc1
    | MulAdd
    | MulLong
    | MulHigh
    | CondSelect
    | CondCompareReg
    | CondCompareImm
    | Branch
    | BranchCond
    | CompareBranch
    | TestBranch
    | BranchReg
    | Nop
    | LoadStore
    | LoadStoreUnscaled
    | Pair
)
type Item = Instr | Label
type Program = tuple[Item, ...]
