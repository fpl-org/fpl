"""The preferred disassembly (C1.4): which alias, if any, prints a base instruction, and back.

Per class, an ordered table of rows, each an alias the C6.2 page of its base instruction
lists, with the condition under which that alias "is preferred" as the spec states it (the
`cite`), plus the operand ranges the condition assumes: an instruction with an out-of-range
or unencodable field matches no row and prints in its base form, so the text still carries
the value. The first row that matches wins, which is also how the spec's overlapping rows
read (UBFM: LSL before UBFIZ; SUBS: CMP before NEGS); none matching, the base form prints.

The text is llvm-objdump's (LLVM 21.1.8, default aliases, decimal immediates) where it
differs from the spec; such rows carry `spec_differs` (hole `alias-divergence`).

Each row also carries `build`, the inverse of its render: from the atoms of an operand text
(`Operands`) back to the base instruction. The parser tries every candidate of a mnemonic and
keeps the one whose reprint is the line it read, so a builder may be lenient.
"""

import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from functools import cache, partial
from typing import Any

from fpl.asm.aarch64.model import (
    Access,
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
    OpLogicalImm,
    OpMoveWide,
    OpMulAdd,
    OpMulHigh,
    OpMulLong,
    OpPair,
    OpTestBranch,
    Pair,
    PostIndex,
    PreIndex,
    Reg,
    RegOffset,
    Shift,
    TestBranch,
    Width,
    names,
    shifted,
)


def decode_bitmask(n: int, immr: int, imms: int, width: Width) -> int | None:
    """DecodeBitMasks (J1.2.214) for a logical immediate at `width`: the value N:immr:imms
    encodes, or None where the encoding is reserved or the element is wider than `width`."""
    length = ((n << 6) | (~imms & 0x3F)).bit_length() - 1
    if length < 1 or 1 << length > width:
        return None
    esize, levels = 1 << length, (1 << length) - 1
    ones, rotate = imms & levels, immr & levels
    if ones == levels:
        return None
    element = (1 << (ones + 1)) - 1
    element = ((element >> rotate) | (element << (esize - rotate))) & ((1 << esize) - 1)
    return sum(element << at for at in range(0, width, esize))


@cache
def encodings(width: Width) -> dict[int, tuple[int, int, int]]:
    """Every encodable value at `width` with its canonical (N, immr, imms): the first in
    (N, immr, imms) order, which is the smallest rotation of the smallest element."""
    table: dict[int, tuple[int, int, int]] = {}
    for n in range(2):
        for immr in range(64):
            for imms in range(64):
                value = decode_bitmask(n, immr, imms, width)
                if value is not None:
                    table.setdefault(value, (n, immr, imms))
    return table


def encode_bitmask(value: int, width: Width) -> tuple[int, int, int] | None:
    """The canonical (N, immr, imms) of `value` as a logical immediate, or None."""
    return encodings(width).get(value)


def signed(value: int, width: Width) -> int:
    """`value` modulo 2^width, read as two's complement."""
    value %= 1 << width
    return value - (1 << width) if value >> (width - 1) else value


def chunk(value: int, width: Width) -> tuple[int, int]:
    """(imm16, hw) with imm16 << 16 * hw == value modulo 2^width; ValueError if none."""
    value %= 1 << width
    for hw in range(width // 16):
        if not value & ~(0xFFFF << (16 * hw)):
            return value >> (16 * hw), hw
    raise ValueError(value)


def wide_movable(value: int, width: Width) -> bool:
    """Whether MOVZ or MOVN makes `value` at `width` in one instruction: one 16-bit chunk
    of it, or of its complement, set (LLVM's isAnyMOVWMovAlias)."""
    value %= 1 << width
    return any(
        not v & ~(0xFFFF << (16 * hw))
        for v in (value, ~value % (1 << width))
        for hw in range(width // 16)
    )


def fits(value: int, bound: int) -> bool:
    """0 <= value < bound."""
    return 0 <= value < bound


WORDS = {*Shift, *Extend, *(cond.text for cond in Cond)}
REGISTERS = {reg.name_at(width): (reg, width) for reg in Reg for width in Width}
TOKEN = re.compile(r"(?P<reg>\b(?:[wx]\d+|w?sp|[wx]zr)\b)|#(?P<num>-?\w+)|(?P<name>\.?\w+)")


def kind(match: re.Match[str]) -> str:
    """A token's letter in an operand shape: register, number, word or label."""
    if match["reg"]:
        return "r"
    if match["num"]:
        return "n"
    return "w" if match["name"] in WORDS else "l"


@dataclass(frozen=True, slots=True)
class Operands:
    """The atoms of an operand text, by kind and in order, and its shape: the text with each
    register as `r`, each immediate as `n`, each word as `w` and each label as `l`."""

    regs: tuple[Reg, ...]
    widths: tuple[Width, ...]
    nums: tuple[int, ...]
    words: tuple[str, ...]
    labels: tuple[Label, ...]
    shape: str

    @classmethod
    def of(cls, text: str) -> "Operands":
        """The atoms of `text`; KeyError or ValueError for a register or number it cannot
        read (the parser then has no candidate)."""
        atoms: dict[str, list[re.Match[str]]] = {"r": [], "n": [], "w": [], "l": []}
        for match in TOKEN.finditer(text):
            atoms[kind(match)].append(match)
        regs = [REGISTERS[match["reg"]] for match in atoms["r"]]
        return cls(
            tuple(reg for reg, _ in regs),
            tuple(width for _, width in regs),
            tuple(int(match["num"], 0) for match in atoms["n"]),
            tuple(match["name"] for match in atoms["w"]),
            tuple(Label(match["name"]) for match in atoms["l"]),
            TOKEN.sub(kind, text),
        )

    @property
    def width(self) -> Width:
        """The first register's width: the instruction's, in every form that has one."""
        return self.widths[0]

    def shift(self) -> tuple[Shift, int]:
        """The trailing `shift #amount`, `lsl #0` when there is none."""
        return (Shift(self.words[0]), self.nums[-1]) if self.words else (Shift.LSL, 0)

    def extend(self) -> tuple[Extend, int]:
        """The trailing extend and amount; `lsl` or none is the width's own extend."""
        word = self.words[0] if self.words else "lsl"
        own = Extend.UXTX if self.width is Width.W64 else Extend.UXTW
        return own if word == "lsl" else Extend(word), self.nums[-1] if self.nums else 0

    def cond(self) -> Cond:
        """The trailing condition."""
        return Cond[self.words[-1].upper()]

    def mode(self) -> Mode:
        """The addressing mode by shape: `]!` pre-index, `], ` post-index, else offset."""
        if self.shape.endswith("]!"):
            return Mode.PRE
        return Mode.POST if "], " in self.shape else Mode.OFFSET


@dataclass(frozen=True, slots=True)
class Row[T: Instr]:
    """One alias of a base page: its mnemonic, the page and condition it is cited from, when
    it is preferred (the condition and the operand ranges it assumes), its operands, and the
    inverse. `spec_differs` marks a row where LLVM's text is not the spec's (alias-divergence)."""

    mnemonic: str
    cite: str
    when: Callable[[T], bool]
    render: Callable[[T], str]
    build: Callable[[Operands], T]
    spec_differs: bool = False


def mov_wide(i: MoveWide) -> bool:
    """imm16 in [0, 65535], hw below width / 16, and not (IsZero(imm16) && hw != '00')."""
    return fits(i.imm16, 1 << 16) and fits(i.hw, i.width // 16) and not (i.imm16 == 0 < i.hw)


def movz_mov(i: MoveWide) -> bool:
    """MOVZ, MOV (wide immediate): !(IsZero(imm16) && hw != '00')."""
    return i.op is OpMoveWide.MOVZ and mov_wide(i)


def movn_mov(i: MoveWide) -> bool:
    """MOVN, MOV (inverted wide immediate): !(IsZero(imm16) && hw != '00'), and at 32 bits
    also !IsOnes(imm16)."""
    ones = i.width is Width.W32 and i.imm16 == 0xFFFF
    return i.op is OpMoveWide.MOVN and mov_wide(i) and not ones


def movz_of(o: Operands) -> MoveWide:
    """MOVZ from `mov rd, #value`."""
    return MoveWide(OpMoveWide.MOVZ, o.width, o.regs[0], *chunk(o.nums[0], o.width))


def movn_of(o: Operands) -> MoveWide:
    """MOVN from `mov rd, #value`."""
    return MoveWide(OpMoveWide.MOVN, o.width, o.regs[0], *chunk(~o.nums[0], o.width))


def moved(i: MoveWide) -> str:
    """`rd, #value`: the value moved, as signed two's-complement decimal at the width."""
    value = i.imm16 << (16 * i.hw)
    if i.op is OpMoveWide.MOVN:
        value = ~value
    return f"{i.rd.name_at(i.width)}, #{signed(value, i.width)}"


def move_wide_rows() -> tuple[Row[MoveWide], ...]:
    """The MoveWide alias rows, in the order they are tried."""
    return (
        Row("mov", "C6.2.285 MOVZ, MOV (wide immediate)", movz_mov, moved, movz_of),
        Row("mov", "C6.2.284 MOVN, MOV (inverted wide immediate)", movn_mov, moved, movn_of),
    )


def orr_mov(i: LogicalImm) -> bool:
    """ORR (immediate), MOV (bitmask immediate), as llvm-objdump prints it: Rn == '11111', the
    value encodable, and no MOVZ or MOVN makes it at the width. The spec's condition,
    !MoveWidePreferred(sf, N, imms, immr), prints mov for some values MOVN makes
    (0xFFFFFFFFFFFEFFFF: imms 62, immr 47), which LLVM prints as orr (alias-divergence)."""
    encodable = encode_bitmask(i.imm, i.width) is not None
    movable = wide_movable(i.imm, i.width)
    return i.op is OpLogicalImm.ORR and i.rn is Reg.ZR and encodable and not movable


def ands_tst(i: LogicalImm) -> bool:
    """ANDS (immediate), TST (immediate): Rd == '11111'; the value encodable."""
    encodable = encode_bitmask(i.imm, i.width) is not None
    return i.op is OpLogicalImm.ANDS and i.rd is Reg.ZR and encodable


def logical_imm_rows() -> tuple[Row[LogicalImm], ...]:
    """The LogicalImm alias rows, in the order they are tried."""
    return (
        Row(
            "mov",
            "C6.2.301 ORR (immediate), MOV (bitmask immediate)",
            orr_mov,
            lambda i: f"{i.rd.name_at(i.width)}, #{signed(i.imm, i.width)}",
            lambda o: LogicalImm(
                OpLogicalImm.ORR, o.width, o.regs[0], Reg.ZR, o.nums[0] % (1 << o.width)
            ),
            spec_differs=True,
        ),
        Row(
            "tst",
            "C6.2.16 ANDS (immediate), TST (immediate)",
            ands_tst,
            lambda i: f"{i.rn.name_at(i.width)}, #{hex(i.imm)}",
            lambda o: LogicalImm(OpLogicalImm.ANDS, o.width, Reg.ZR, o.regs[0], o.nums[0]),
        ),
    )


def shift_ok(i: LogicalShifted | AddSubShifted) -> bool:
    """The shift amount below the width; add and sub also refuse ror."""
    ror = isinstance(i, AddSubShifted) and i.shift is Shift.ROR
    return fits(i.amount, i.width) and not ror


def orr_mov_reg(i: LogicalShifted) -> bool:
    """ORR (shifted register), MOV (register): shift == '00' && imm6 == '000000' &&
    Rn == '11111'."""
    unshifted = i.shift is Shift.LSL and i.amount == 0
    return i.op is OpLogical.ORR and i.rn is Reg.ZR and unshifted


def orn_mvn(i: LogicalShifted) -> bool:
    """ORN (shifted register), MVN: Rn == '11111'."""
    return i.op is OpLogical.ORN and i.rn is Reg.ZR and shift_ok(i)


def ands_tst_reg(i: LogicalShifted) -> bool:
    """ANDS (shifted register), TST (shifted register): Rd == '11111'."""
    return i.op is OpLogical.ANDS and i.rd is Reg.ZR and shift_ok(i)


def logical_of(op: OpLogical, o: Operands, rd: Reg, rn: Reg) -> LogicalShifted:
    """The logical instruction with the text's last register and shift."""
    return LogicalShifted(op, o.width, rd, rn, o.regs[-1], *o.shift())


def rest(i: LogicalShifted | AddSubShifted, rd: Reg) -> str:
    """`first, rm{, shift #amount}`: an alias's operands with one register left out."""
    return names(i.width, rd, i.rm) + shifted(i.shift, i.amount)


def logical_shifted_rows() -> tuple[Row[LogicalShifted], ...]:
    """The LogicalShifted alias rows, in the order they are tried."""
    return (
        Row(
            "mov",
            "C6.2.302 ORR (shifted register), MOV (register)",
            orr_mov_reg,
            lambda i: names(i.width, i.rd, i.rm),
            lambda o: logical_of(OpLogical.ORR, o, o.regs[0], Reg.ZR),
        ),
        Row(
            "mvn",
            "C6.2.300 ORN (shifted register), MVN",
            orn_mvn,
            lambda i: rest(i, i.rd),
            lambda o: logical_of(OpLogical.ORN, o, o.regs[0], Reg.ZR),
        ),
        Row(
            "tst",
            "C6.2.17 ANDS (shifted register), TST (shifted register)",
            ands_tst_reg,
            lambda i: rest(i, i.rn),
            lambda o: logical_of(OpLogical.ANDS, o, Reg.ZR, o.regs[0]),
        ),
    )


def add_mov(i: AddSubImm) -> bool:
    """ADD (immediate), MOV (to/from SP): shift == '0' && imm12 == '000000000000' &&
    (Rd == '11111' || Rn == '11111'), 31 being sp in both slots."""
    unshifted = i.imm == 0 and not i.lsl12
    return i.op is OpAddSub.ADD and unshifted and Reg.SP in (i.rd, i.rn)


def compare_imm(op: OpAddSub) -> Callable[[AddSubImm], bool]:
    """ADDS or SUBS (immediate), CMN or CMP (immediate): Rd == '11111'; imm in [0, 4095]."""
    return lambda i: i.op is op and i.rd is Reg.ZR and fits(i.imm, 1 << 12)


def compared_imm(i: AddSubImm) -> str:
    """`rn, #imm{, lsl #12}`."""
    return i.operands().partition(", ")[2]


def compare_imm_of(op: OpAddSub, o: Operands) -> AddSubImm:
    """CMN or CMP from `rn, #imm{, lsl #12}`."""
    return AddSubImm(op, o.width, Reg.ZR, o.regs[0], o.nums[0], "lsl" in o.words)


def add_sub_imm_rows() -> tuple[Row[AddSubImm], ...]:
    """The AddSubImm alias rows, in the order they are tried."""
    return (
        Row(
            "mov",
            "C6.2.5 ADD (immediate), MOV (to/from SP)",
            add_mov,
            lambda i: names(i.width, i.rd, i.rn),
            lambda o: AddSubImm(OpAddSub.ADD, o.width, o.regs[0], o.regs[1], 0, lsl12=False),
        ),
        Row(
            "cmn",
            "C6.2.10 ADDS (immediate), CMN (immediate)",
            compare_imm(OpAddSub.ADDS),
            compared_imm,
            partial(compare_imm_of, OpAddSub.ADDS),
        ),
        Row(
            "cmp",
            "C6.2.464 SUBS (immediate), CMP (immediate)",
            compare_imm(OpAddSub.SUBS),
            compared_imm,
            partial(compare_imm_of, OpAddSub.SUBS),
        ),
    )


def shifted_row(op: OpAddSub, slot: str) -> Callable[[AddSubShifted], bool]:
    """ADDS, SUBS or SUB (shifted register) with the zero register in `slot` (rd for CMN and
    CMP, rn for NEG and NEGS); the shift lsl, lsr or asr, below the width."""
    return lambda i: i.op is op and getattr(i, slot) is Reg.ZR and shift_ok(i)


def add_sub_of(op: OpAddSub, zero: str, o: Operands) -> AddSubShifted:
    """The add or sub whose `zero` slot (rd or rn) is the zero register the alias drops."""
    first, rm = o.regs[0], o.regs[1]
    rd, rn = (Reg.ZR, first) if zero == "rd" else (first, Reg.ZR)
    return AddSubShifted(op, o.width, rd, rn, rm, *o.shift())


def add_sub_row(mnemonic: str, cite: str, op: OpAddSub, zero: str) -> Row[AddSubShifted]:
    """A shifted-register alias that drops the zero register in `zero`."""
    keep = "rn" if zero == "rd" else "rd"
    return Row(
        mnemonic,
        cite,
        shifted_row(op, zero),
        lambda i: rest(i, getattr(i, keep)),
        partial(add_sub_of, op, zero),
    )


def add_sub_shifted_rows() -> tuple[Row[AddSubShifted], ...]:
    """The AddSubShifted alias rows, in the order they are tried."""
    return (
        add_sub_row(
            "cmn",
            "C6.2.11 ADDS (shifted register), CMN (shifted register): Rd == '11111'",
            OpAddSub.ADDS,
            "rd",
        ),
        add_sub_row(
            "cmp",
            "C6.2.465 SUBS (shifted register), CMP (shifted register): Rd == '11111'",
            OpAddSub.SUBS,
            "rd",
        ),
        add_sub_row(
            "neg",
            "C6.2.458 SUB (shifted register), NEG (shifted register): Rn == '11111'",
            OpAddSub.SUB,
            "rn",
        ),
        add_sub_row(
            "negs", "C6.2.465 SUBS (shifted register), NEGS: Rn == '11111'", OpAddSub.SUBS, "rn"
        ),
    )


def compare_extended(op: OpAddSub) -> Callable[[AddSubExtended], bool]:
    """ADDS or SUBS (extended register), CMN or CMP (extended register): Rd == '11111';
    the amount in [0, 4]."""
    return lambda i: i.op is op and i.rd is Reg.ZR and fits(i.amount, 5)


def compare_extended_of(op: OpAddSub, o: Operands) -> AddSubExtended:
    """CMN or CMP from `rn, rm{, extend #amount}`."""
    return AddSubExtended(op, o.width, Reg.ZR, o.regs[0], o.regs[1], *o.extend())


def compared_extended(i: AddSubExtended) -> str:
    """`rn, rm{, extend #amount}`."""
    return f"{i.rn.name_at(i.width)}, {i.rm_name()}{i.extension()}"


def add_sub_extended_rows() -> tuple[Row[AddSubExtended], ...]:
    """The AddSubExtended alias rows, in the order they are tried."""
    return (
        Row(
            "cmn",
            "C6.2.9 ADDS (extended register), CMN (extended register): Rd == '11111'",
            compare_extended(OpAddSub.ADDS),
            compared_extended,
            partial(compare_extended_of, OpAddSub.ADDS),
        ),
        Row(
            "cmp",
            "C6.2.463 SUBS (extended register), CMP (extended register): Rd == '11111'",
            compare_extended(OpAddSub.SUBS),
            compared_extended,
            partial(compare_extended_of, OpAddSub.SUBS),
        ),
    )


def negate_carry(op: OpAddSubCarry) -> Callable[[AddSubCarry], bool]:
    """SBC or SBCS, NGC or NGCS: Rn == '11111'."""
    return lambda i: i.op is op and i.rn is Reg.ZR


def carry_of(op: OpAddSubCarry, o: Operands) -> AddSubCarry:
    """NGC or NGCS from `rd, rm`."""
    return AddSubCarry(op, o.width, o.regs[0], Reg.ZR, o.regs[1])


def add_sub_carry_rows() -> tuple[Row[AddSubCarry], ...]:
    """The AddSubCarry alias rows, in the order they are tried."""
    return (
        Row(
            "ngc",
            "C6.2.352 SBC, NGC: Rn == '11111'",
            negate_carry(OpAddSubCarry.SBC),
            lambda i: names(i.width, i.rd, i.rm),
            partial(carry_of, OpAddSubCarry.SBC),
        ),
        Row(
            "ngcs",
            "C6.2.353 SBCS, NGCS: Rn == '11111'",
            negate_carry(OpAddSubCarry.SBCS),
            lambda i: names(i.width, i.rd, i.rm),
            partial(carry_of, OpAddSubCarry.SBCS),
        ),
    )


def bitfield(op: OpBitfield, i: Bitfield) -> bool:
    """The op, and immr and imms below the width."""
    return i.op is op and fits(i.immr, i.width) and fits(i.imms, i.width)


def bfx_preferred(i: Bitfield) -> bool:
    """BFXPreferred(sf, opc<1>, imms, immr) (J1.2): not UBFIZ/SBFIZ, LSR/ASR, UXT*/SXT*."""
    extends = (7, 15) if i.width is Width.W32 else (7, 15, 31)
    signed_x = i.op is OpBitfield.SBFM or i.width is Width.W32
    extension = i.immr == 0 and signed_x and i.imms in extends
    return i.immr <= i.imms < i.width - 1 and not extension


def shift_of(op: OpBitfield, o: Operands) -> Bitfield:
    """ASR or LSR (immediate) from `rd, rn, #shift`: immr = shift, imms = width - 1."""
    return Bitfield(op, o.width, o.regs[0], o.regs[1], o.nums[0], o.width - 1)


def lsl_of(o: Operands) -> Bitfield:
    """LSL (immediate) from `rd, rn, #shift`: UBFM #(-shift MOD width), #(width - 1 - shift)."""
    shift = o.nums[0]
    return Bitfield(
        OpBitfield.UBFM, o.width, o.regs[0], o.regs[1], -shift % o.width, o.width - 1 - shift
    )


def insert_of(op: OpBitfield, o: Operands) -> Bitfield:
    """*BFIZ or BFI from `rd, rn, #lsb, #width`: immr = -lsb MOD width, imms = width - 1."""
    lsb, bits = o.nums
    return Bitfield(op, o.width, o.regs[0], o.regs[1], -lsb % o.width, bits - 1)


def extract_of(op: OpBitfield, o: Operands) -> Bitfield:
    """*BFX or BFXIL from `rd, rn, #lsb, #width`: immr = lsb, imms = lsb + width - 1."""
    lsb, bits = o.nums
    return Bitfield(op, o.width, o.regs[0], o.regs[1], lsb, lsb + bits - 1)


def extend_of(op: OpBitfield, imms: int, o: Operands) -> Bitfield:
    """SXT* or UXT* from `rd, wn`: immr = 0."""
    return Bitfield(op, o.width, o.regs[0], o.regs[1], 0, imms)


def inserted(i: Bitfield) -> str:
    """`rd, rn, #lsb, #width` of an insert: lsb = -immr MOD width, width = imms + 1."""
    return f"{names(i.width, i.rd, i.rn)}, #{-i.immr % i.width}, #{i.imms + 1}"


def extracted(i: Bitfield) -> str:
    """`rd, rn, #lsb, #width` of an extract: lsb = immr, width = imms - immr + 1."""
    return f"{names(i.width, i.rd, i.rn)}, #{i.immr}, #{i.imms - i.immr + 1}"


def extension(i: Bitfield) -> str:
    """`rd, wn`: the source is always a w register."""
    return f"{i.rd.name_at(i.width)}, {i.rn.name_at(Width.W32)}"


def extend_row(op: OpBitfield, mnemonic: str, imms: int, cite: str) -> Row[Bitfield]:
    """SXTB, SXTH, SXTW, UXTB or UXTH: immr == '000000' && imms == `imms`; UXT* and the
    32-bit SXT* forms exist at 32 bits (sxtb, sxth) and SXTW at 64 bits only."""
    widths = {"sxtw": (Width.W64,), "uxtb": (Width.W32,), "uxth": (Width.W32,)}
    at = widths.get(mnemonic, tuple(Width))
    return Row(
        mnemonic,
        cite,
        lambda i: bitfield(op, i) and i.width in at and i.immr == 0 and i.imms == imms,
        extension,
        partial(extend_of, op, imms),
    )


SBFM, BFM, UBFM = OpBitfield.SBFM, OpBitfield.BFM, OpBitfield.UBFM


def bitfield_rows() -> tuple[Row[Bitfield], ...]:
    """The Bitfield alias rows, in the order they are tried."""
    return (
        Row(
            "asr",
            "C6.2.355 SBFM, ASR (immediate): imms == sf:'11111'",
            lambda i: bitfield(SBFM, i) and i.imms == i.width - 1,
            lambda i: f"{names(i.width, i.rd, i.rn)}, #{i.immr}",
            partial(shift_of, SBFM),
        ),
        Row(
            "sbfiz",
            "C6.2.355 SBFM, SBFIZ: UInt(imms) < UInt(immr)",
            lambda i: bitfield(SBFM, i) and i.imms < i.immr,
            inserted,
            partial(insert_of, SBFM),
        ),
        Row(
            "sbfx",
            "C6.2.355 SBFM, SBFX: BFXPreferred(sf, opc<1>, imms, immr)",
            lambda i: bitfield(SBFM, i) and bfx_preferred(i),
            extracted,
            partial(extract_of, SBFM),
        ),
        extend_row(SBFM, "sxtb", 7, "C6.2.355 SBFM, SXTB: immr == '000000' && imms == '000111'"),
        extend_row(SBFM, "sxth", 15, "C6.2.355 SBFM, SXTH: immr == '000000' && imms == '001111'"),
        extend_row(SBFM, "sxtw", 31, "C6.2.355 SBFM, SXTW: immr == '000000' && imms == '011111'"),
        Row(
            "bfi",
            "C6.2.39 BFM, BFI: Rn != '11111' && UInt(imms) < UInt(immr)",
            lambda i: bitfield(BFM, i) and i.rn is not Reg.ZR and i.imms < i.immr,
            inserted,
            partial(insert_of, BFM),
        ),
        Row(
            "bfi",
            "C6.2.39 BFM, BFC: Rn == '11111' && UInt(imms) < UInt(immr); llvm-objdump prints bfi",
            lambda i: bitfield(BFM, i) and i.rn is Reg.ZR and i.imms < i.immr,
            inserted,
            partial(insert_of, BFM),
            spec_differs=True,
        ),
        Row(
            "bfxil",
            "C6.2.39 BFM, BFXIL: UInt(imms) >= UInt(immr)",
            lambda i: bitfield(BFM, i) and i.imms >= i.immr,
            extracted,
            partial(extract_of, BFM),
        ),
        Row(
            "lsl",
            "C6.2.487 UBFM, LSL (immediate): imms != sf:'11111' && imms + 1 == immr",
            lambda i: bitfield(UBFM, i) and i.imms != i.width - 1 and i.imms + 1 == i.immr,
            lambda i: f"{names(i.width, i.rd, i.rn)}, #{i.width - 1 - i.imms}",
            lsl_of,
        ),
        Row(
            "lsr",
            "C6.2.487 UBFM, LSR (immediate): imms == sf:'11111'",
            lambda i: bitfield(UBFM, i) and i.imms == i.width - 1,
            lambda i: f"{names(i.width, i.rd, i.rn)}, #{i.immr}",
            partial(shift_of, UBFM),
        ),
        Row(
            "ubfiz",
            "C6.2.487 UBFM, UBFIZ: UInt(imms) < UInt(immr)",
            lambda i: bitfield(UBFM, i) and i.imms < i.immr,
            inserted,
            partial(insert_of, UBFM),
        ),
        Row(
            "ubfx",
            "C6.2.487 UBFM, UBFX: BFXPreferred(sf, opc<1>, imms, immr)",
            lambda i: bitfield(UBFM, i) and bfx_preferred(i),
            extracted,
            partial(extract_of, UBFM),
        ),
        extend_row(UBFM, "uxtb", 7, "C6.2.487 UBFM, UXTB: immr == '000000' && imms == '000111'"),
        extend_row(UBFM, "uxth", 15, "C6.2.487 UBFM, UXTH: immr == '000000' && imms == '001111'"),
    )


def extract_rows() -> tuple[Row[Extract], ...]:
    """The Extract alias rows, in the order they are tried."""
    return (
        Row(
            "ror",
            "C6.2.160 EXTR, ROR (immediate): Rn == Rm",
            lambda i: i.rn is i.rm and fits(i.lsb, i.width),
            lambda i: f"{names(i.width, i.rd, i.rn)}, #{i.lsb}",
            lambda o: Extract(o.width, o.regs[0], o.regs[1], o.regs[1], o.nums[0]),
        ),
    )


def three_of[T](make: Callable[[Any, Width, Reg, Reg, Reg], T], op: Any, o: Operands) -> T:
    """An instruction of three registers at the width: `rd, rn, rm`."""
    return make(op, o.width, o.regs[0], o.regs[1], o.regs[2])


def mul_add_of(op: OpMulAdd, o: Operands, ra: int = 3) -> MulAdd:
    """MADD, MSUB from `rd, rn, rm, ra`; MUL, MNEG (`ra` past the end) with the zero register."""
    acc = o.regs[ra] if ra < len(o.regs) else Reg.ZR
    return MulAdd(op, o.width, o.regs[0], o.regs[1], o.regs[2], acc)


def mul_long_of(op: OpMulLong, o: Operands, ra: int = 3) -> MulLong:
    """The widening multiplies from `xd, wn, wm, xa`, or without xa the zero register."""
    acc = o.regs[ra] if ra < len(o.regs) else Reg.ZR
    return MulLong(op, o.regs[0], o.regs[1], o.regs[2], acc)


def variable_row(op: OpDataProc2, mnemonic: str, cite: str) -> Row[DataProc2]:
    """A shift by register: the alias is preferred unconditionally."""
    return Row(
        mnemonic,
        cite,
        lambda i: i.op is op,
        DataProc2.operands,
        partial(three_of, DataProc2, op),
    )


def data_proc2_rows() -> tuple[Row[DataProc2], ...]:
    """The DataProc2 alias rows, in the order they are tried."""
    return (
        variable_row(OpDataProc2.LSLV, "lsl", "C6.2.271 LSLV, LSL (register): unconditionally"),
        variable_row(OpDataProc2.LSRV, "lsr", "C6.2.274 LSRV, LSR (register): unconditionally"),
        variable_row(OpDataProc2.ASRV, "asr", "C6.2.21 ASRV, ASR (register): unconditionally"),
        variable_row(OpDataProc2.RORV, "ror", "C6.2.349 RORV, ROR (register): unconditionally"),
    )


def accumulates_zero(op: OpMulAdd | OpMulLong, i: MulAdd | MulLong) -> bool:
    """The op, with Ra == '11111': the zero register as accumulator."""
    return i.op is op and i.ra is Reg.ZR


def product(i: MulAdd) -> str:
    """`rd, rn, rm`: the operands without the zero accumulator."""
    return names(i.width, i.rd, i.rn, i.rm)


def long_product(i: MulLong) -> str:
    """`xd, wn, wm`: the operands without the zero accumulator."""
    return f"{i.rd.name_at(Width.W64)}, {names(Width.W32, i.rn, i.rm)}"


MADD, MSUB = OpMulAdd.MADD, OpMulAdd.MSUB
SMADDL, SMSUBL, UMADDL, UMSUBL = OpMulLong


def mul_add_rows() -> tuple[Row[MulAdd], ...]:
    """The MulAdd alias rows, in the order they are tried."""
    return (
        Row("mul", "C6.2.275 MADD, MUL: Ra == '11111'", partial(accumulates_zero, MADD), product,
            partial(mul_add_of, MADD)),
        Row("mneg", "C6.2.291 MSUB, MNEG: Ra == '11111'", partial(accumulates_zero, MSUB), product,
            partial(mul_add_of, MSUB)),
    )  # fmt: skip


def mul_long_rows() -> tuple[Row[MulLong], ...]:
    """The MulLong alias rows, in the order they are tried."""
    return (
        Row("smull", "C6.2.369 SMADDL, SMULL: Ra == '11111'", partial(accumulates_zero, SMADDL),
            long_product, partial(mul_long_of, SMADDL)),
        Row("smnegl", "C6.2.378 SMSUBL, SMNEGL: Ra == '11111'", partial(accumulates_zero, SMSUBL),
            long_product, partial(mul_long_of, SMSUBL)),
        Row("umull", "C6.2.491 UMADDL, UMULL: Ra == '11111'", partial(accumulates_zero, UMADDL),
            long_product, partial(mul_long_of, UMADDL)),
        Row("umnegl", "C6.2.497 UMSUBL, UMNEGL: Ra == '11111'", partial(accumulates_zero, UMSUBL),
            long_product, partial(mul_long_of, UMSUBL)),
    )  # fmt: skip


def settable(i: CondSelect) -> bool:
    """cond != '111x': neither al nor nv, which have no inverse to print."""
    return i.cond not in (Cond.AL, Cond.NV)


def set_row(op: OpCondSelect, mnemonic: str, cite: str) -> Row[CondSelect]:
    """CSET or CSETM: Rm == '11111' && cond != '111x' && Rn == '11111'."""
    return Row(
        mnemonic,
        cite,
        lambda i: i.op is op and i.rn is i.rm is Reg.ZR and settable(i),
        lambda i: f"{i.rd.name_at(i.width)}, {i.cond.inverse().text}",
        lambda o: CondSelect(op, o.width, o.regs[0], Reg.ZR, Reg.ZR, o.cond().inverse()),
    )


def same_row(op: OpCondSelect, mnemonic: str, cite: str, *, zero: bool) -> Row[CondSelect]:
    """CINC, CINV (Rn == Rm, neither '11111') or CNEG (`zero`: Rn == Rm, any register);
    cond != '111x'."""
    return Row(
        mnemonic,
        cite,
        lambda i: i.op is op and i.rn is i.rm and (zero or i.rn is not Reg.ZR) and settable(i),
        lambda i: f"{names(i.width, i.rd, i.rn)}, {i.cond.inverse().text}",
        lambda o: CondSelect(op, o.width, o.regs[0], o.regs[1], o.regs[1], o.cond().inverse()),
    )


CSINC, CSINV, CSNEG = OpCondSelect.CSINC, OpCondSelect.CSINV, OpCondSelect.CSNEG


def cond_select_rows() -> tuple[Row[CondSelect], ...]:
    """The CondSelect alias rows, in the order they are tried."""
    return (
        set_row(
            CSINC, "cset", "C6.2.141 CSINC, CSET: Rm == '11111' && cond != '111x' && Rn == '11111'"
        ),
        same_row(
            CSINC,
            "cinc",
            "C6.2.141 CSINC, CINC: Rm != '11111' && cond != '111x' && Rn != '11111' && Rn == Rm",
            zero=False,
        ),
        set_row(
            CSINV,
            "csetm",
            "C6.2.142 CSINV, CSETM: Rm == '11111' && cond != '111x' && Rn == '11111'",
        ),
        same_row(
            CSINV,
            "cinv",
            "C6.2.142 CSINV, CINV: Rm != '11111' && cond != '111x' && Rn != '11111' && Rn == Rm",
            zero=False,
        ),
        same_row(CSNEG, "cneg", "C6.2.143 CSNEG, CNEG: cond != '111x' && Rn == Rm", zero=True),
    )


@cache
def rows() -> dict[type, tuple[Row[Any], ...]]:
    """Every class's alias rows, built on the first call rather than at import, so a
    mutant of a row builder runs in the tests that read the rows."""
    return {
        MoveWide: move_wide_rows(),
        LogicalImm: logical_imm_rows(),
        AddSubImm: add_sub_imm_rows(),  # before ORR's mov: `mov x1, sp` is ADD
        LogicalShifted: logical_shifted_rows(),
        # before shifted: `cmn wsp, wzr` is extended
        AddSubExtended: add_sub_extended_rows(),
        AddSubShifted: add_sub_shifted_rows(),
        AddSubCarry: add_sub_carry_rows(),
        Bitfield: bitfield_rows(),
        Extract: extract_rows(),
        DataProc2: data_proc2_rows(),
        MulAdd: mul_add_rows(),
        MulLong: mul_long_rows(),
        CondSelect: cond_select_rows(),
    }


def fired(instr: Instr) -> Row[Any] | None:
    """The first row of `instr`'s class whose condition holds, if any."""
    return next((row for row in rows().get(type(instr), ()) if row.when(instr)), None)


def mnemonic(instr: Instr) -> str:
    """The base form's mnemonic."""
    match instr:
        case LoadStore() | LoadStoreUnscaled():
            return instr.op.mnemonic
        case BranchCond():
            return instr.MNEMONIC + instr.cond.text
        case Extract() | Adr() | Nop():
            return instr.MNEMONIC
        case _:
            return instr.op.value


def preferred(instr: Instr) -> tuple[str, str]:
    """The mnemonic and operands llvm-objdump prints for `instr`."""
    row = fired(instr)
    if row is None:
        return mnemonic(instr), instr.operands()
    return row.mnemonic, row.render(instr)


def addr_of(o: Operands) -> Addr:
    """A single register's address: register offset when a second register follows rt."""
    rn = o.regs[1]
    if len(o.regs) > 2:
        word = o.words[0] if o.words else "lsl"
        option = Extend.UXTX if word == "lsl" else Extend(word)
        return RegOffset(rn, o.regs[2], option, bool(o.nums))
    return ADDRESSES[o.mode()](rn, o.nums[0] if o.nums else 0)


ADDRESSES: dict[Mode, Callable[[Reg, int], Addr]] = {
    Mode.OFFSET: Offset,
    Mode.PRE: PreIndex,
    Mode.POST: PostIndex,
}


def imm_of(op: OpAddSub, o: Operands) -> AddSubImm:
    """ADD, ADDS, SUB, SUBS (immediate) from `rd, rn, #imm{, lsl #12}`."""
    return AddSubImm(op, o.width, o.regs[0], o.regs[1], o.nums[0], "lsl" in o.words)


def extended_of(op: OpAddSub, o: Operands) -> AddSubExtended:
    """ADD, ADDS, SUB, SUBS (extended register) from `rd, rn, rm{, extend #amount}`."""
    return AddSubExtended(op, o.width, o.regs[0], o.regs[1], o.regs[2], *o.extend())


def shifted_of(op: OpAddSub, o: Operands) -> AddSubShifted:
    """ADD, ADDS, SUB, SUBS (shifted register) from `rd, rn, rm{, shift #amount}`."""
    return AddSubShifted(op, o.width, o.regs[0], o.regs[1], o.regs[2], *o.shift())


def logical_base_of(op: OpLogical, o: Operands) -> LogicalShifted:
    """A logical (shifted register) base form from `rd, rn, rm{, shift #amount}`."""
    return logical_of(op, o, o.regs[0], o.regs[1])


def move_wide_of(op: OpMoveWide, o: Operands) -> MoveWide:
    """MOVN, MOVZ, MOVK from `rd, #imm16{, lsl #shift}`."""
    return MoveWide(op, o.width, o.regs[0], o.nums[0], o.nums[1] // 16 if o.words else 0)


def bitfield_of(op: OpBitfield, o: Operands) -> Bitfield:
    """SBFM, BFM, UBFM from `rd, rn, #immr, #imms`."""
    return Bitfield(op, o.width, o.regs[0], o.regs[1], o.nums[0], o.nums[1])


def mul_high_of(op: OpMulHigh, o: Operands) -> MulHigh:
    """SMULH, UMULH from `xd, xn, xm`."""
    return MulHigh(op, o.regs[0], o.regs[1], o.regs[2])


def select_of(op: OpCondSelect, o: Operands) -> CondSelect:
    """The conditional selects from `rd, rn, rm, cond`."""
    return CondSelect(op, o.width, o.regs[0], o.regs[1], o.regs[2], o.cond())


def compare_reg_of(op: OpCondCompare, o: Operands) -> CondCompareReg:
    """CCMN, CCMP (register) from `rn, rm, #nzcv, cond`."""
    return CondCompareReg(op, o.width, o.regs[0], o.regs[1], o.nums[0], o.cond())


def compare_imm5_of(op: OpCondCompare, o: Operands) -> CondCompareImm:
    """CCMN, CCMP (immediate) from `rn, #imm5, #nzcv, cond`."""
    return CondCompareImm(op, o.width, o.regs[0], o.nums[0], o.nums[1], o.cond())


def branch_of(op: OpBranch, o: Operands) -> Branch:
    """B, BL from `label`."""
    return Branch(op, o.labels[0])


def compare_branch_of(op: OpCompareBranch, o: Operands) -> CompareBranch:
    """CBZ, CBNZ from `rt, label`."""
    return CompareBranch(op, o.width, o.regs[0], o.labels[0])


def test_branch_of(op: OpTestBranch, o: Operands) -> TestBranch:
    """TBZ, TBNZ from `rt, #bit, label`."""
    return TestBranch(op, o.regs[0], o.nums[0], o.labels[0])


def branch_reg_of(op: OpBranchReg, o: Operands) -> BranchReg:
    """BR, BLR, RET from `xn`, or RET from nothing (x30)."""
    return BranchReg(op, o.regs[0] if o.regs else Reg.X30)


def load_store_of(op: OpLoadStore, o: Operands) -> LoadStore:
    """A load or store from `rt, address`."""
    return LoadStore(op, o.regs[0], addr_of(o))


def unscaled_of(op: OpLoadStoreUnscaled, o: Operands) -> LoadStoreUnscaled:
    """STUR*, LDUR* from `rt, [rn{, #simm9}]`."""
    return LoadStoreUnscaled(op, o.regs[0], o.regs[1], o.nums[0] if o.nums else 0)


def pair_of(op: OpPair, o: Operands) -> Pair:
    """STP, LDP, LDPSW from `rt, rt2, address`."""
    imm = o.nums[0] if o.nums else 0
    return Pair(op, o.width, o.regs[0], o.regs[1], o.regs[2], imm, o.mode())


def extract_base_of(o: Operands) -> Extract:
    """EXTR from `rd, rn, rm, #lsb`."""
    return Extract(o.width, o.regs[0], o.regs[1], o.regs[2], o.nums[0])


def adr_of(o: Operands) -> Adr:
    """ADR from `xd, label`."""
    return Adr(o.regs[0], o.labels[0])


def nop_of(_: Operands) -> Nop:
    """NOP from nothing."""
    return Nop()


def branch_cond_of(cond: Cond, o: Operands) -> BranchCond:
    """B.cond from `label`."""
    return BranchCond(cond, o.labels[0])


# Base forms, per op enum: extended before shifted, so `add x1, sp, x3` reads as the
# extended form it is (sp has no shifted-register text).
BASES: tuple[tuple[type[StrEnum], Callable[[Any, Operands], Instr]], ...] = (
    (OpAddSub, imm_of),
    (OpAddSub, extended_of),
    (OpAddSub, shifted_of),
    (OpAddSubCarry, partial(three_of, AddSubCarry)),
    (OpLogicalImm, lambda op, o: LogicalImm(op, o.width, o.regs[0], o.regs[1], o.nums[0])),
    (OpLogical, logical_base_of),
    (OpMoveWide, move_wide_of),
    (OpBitfield, bitfield_of),
    (OpDataProc2, partial(three_of, DataProc2)),
    (OpDataProc1, lambda op, o: DataProc1(op, o.width, o.regs[0], o.regs[1])),
    (OpMulAdd, mul_add_of),
    (OpMulLong, mul_long_of),
    (OpMulHigh, mul_high_of),
    (OpCondSelect, select_of),
    (OpCondCompare, compare_reg_of),
    (OpCondCompare, compare_imm5_of),
    (OpBranch, branch_of),
    (OpCompareBranch, compare_branch_of),
    (OpTestBranch, test_branch_of),
    (OpBranchReg, branch_reg_of),
    (OpLoadStore, load_store_of),
    (OpLoadStoreUnscaled, unscaled_of),
    (OpPair, pair_of),
)
SINGLES: dict[str, Callable[[Operands], Instr]] = {
    "extr": extract_base_of,
    "adr": adr_of,
    "nop": nop_of,
    **{f"b.{cond.text}": partial(branch_cond_of, cond) for cond in Cond},
}


@cache
def candidates() -> dict[str, list[Callable[[Operands], Instr]]]:
    """Every reading of every mnemonic, alias rows first: the parser keeps the one whose
    reprint is the line."""
    table: defaultdict[str, list[Callable[[Operands], Instr]]] = defaultdict(list)
    for group in rows().values():
        for row in group:
            table[row.mnemonic].append(row.build)
    for ops, build in BASES:
        for op in ops:
            table[op.mnemonic if isinstance(op, Access) else op.value].append(partial(build, op))
    for name, single in SINGLES.items():
        table[name].append(single)
    return dict(table)
