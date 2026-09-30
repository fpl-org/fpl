"""The operand-form checker (design section 4): `check(program)` names every item whose
operands the encoding cannot hold, with the kind of the violation.

The model holds plain integers and any register in any slot, so it can carry an out-of-range
immediate, an unencodable logical immediate, sp where the page names the zero register, or a
branch whose label is out of reach; `check` is where they are refused. A `Problem` has the
item's index, or None for a whole-program problem (an undefined label, which llvm-mc too
reports with no line). The ranges are the C6.2 pages'; each kind lists the pages it reads.

`check` refuses more than llvm-mc 21.1.8 does in two places, both on purpose: the values llvm-mc
silently rewrites into another instruction (`add x1, x2, #4096` becomes `#1, lsl #12`,
`ldr x1, [x2, #3]` becomes `ldur`), since the printed line would not be the instruction
assembled; and the five CONSTRAINED UNPREDICTABLE pair forms llvm-mc accepts (K1.2.17.7, .9,
.19). Register conventions (x18, x29) are not the ISA's and are not checked.
"""

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, fields, is_dataclass
from enum import StrEnum
from typing import Any, assert_never

from fpl.asm.aarch64.alias import encode_bitmask
from fpl.asm.aarch64.model import (
    AddSubExtended,
    AddSubImm,
    AddSubShifted,
    Adr,
    Bitfield,
    Branch,
    BranchCond,
    CompareBranch,
    CondCompareImm,
    CondCompareReg,
    DataProc1,
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
    Offset,
    OpAddSub,
    OpDataProc1,
    OpLogicalImm,
    OpPair,
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


class Kind(StrEnum):
    """What is wrong with an item (design section 4's table)."""

    IMM12 = "imm12"  # AddSubImm.imm in [0, 4095] (C6.2.5 and its siblings)
    BITMASK = "bitmask"  # LogicalImm.imm encodable by DecodeBitMasks (J1.2.214)
    SHIFT_AMOUNT = "shift_amount"  # below the width; ror in the logical forms only
    EXTEND_AMOUNT = "extend_amount"  # [0, 4]; a register offset's option uxtw uxtx sxtw sxtx
    MOVE_WIDE = "move_wide"  # imm16 in [0, 65535], hw below width / 16
    BITFIELD = "bitfield"  # immr, imms, lsb below the width; a test bit in [0, 63]
    COND_IMM = "cond_imm"  # imm5 in [0, 31], nzcv in [0, 15]
    OFFSET = "offset"  # scaled unsigned offsets, simm9, pair imm7 times the size
    REG31 = "reg31"  # sp where the slot names the zero register, or the reverse (C6.1.3)
    WIDTH = "width"  # a width the encoding fixes: rev32 and ldpsw are 64-bit only
    UNPREDICTABLE = "unpredictable"  # K1.2.17: writeback onto a transfer register, rt == rt2
    DUPLICATE_LABEL = "duplicate_label"
    UNDEFINED_LABEL = "undefined_label"
    LABEL_NAME = "label_name"  # ^\.L[A-Za-z0-9_]+$: assembler-local on ELF and Mach-O
    BRANCH_RANGE = "branch_range"


@dataclass(frozen=True, slots=True)
class Problem:
    """A violation: the item's index (None for the program), its kind, and what it is."""

    index: int | None
    kind: Kind
    detail: str


type Found = tuple[tuple[Kind, str], ...]


def need(ok: bool, kind: Kind, detail: str) -> Found:
    """Nothing when `ok`, else the one violation."""
    return () if ok else ((kind, detail),)


def below(value: int, bound: int) -> bool:
    """0 <= value < bound."""
    return 0 <= value < bound


def add_sub_imm(i: AddSubImm) -> Found:
    """C6.2.5, .10, .457, .464: imm12, whatever lsl12 says."""
    return need(below(i.imm, 4096), Kind.IMM12, f"#{i.imm} is not in [0, 4095]")


def add_sub_shifted(i: AddSubShifted) -> Found:
    """C6.2.6, .11, .458, .465: lsl, lsr or asr, the amount below the width."""
    ok = i.shift is not Shift.ROR and below(i.amount, i.width)
    return need(ok, Kind.SHIFT_AMOUNT, f"{i.shift} #{i.amount} at {i.width} bits")


def add_sub_extended(i: AddSubExtended) -> Found:
    """C6.2.4, .9, .456, .463: the extend's left shift in [0, 4]."""
    return need(below(i.amount, 5), Kind.EXTEND_AMOUNT, f"#{i.amount} is not in [0, 4]")


def logical_imm(i: LogicalImm) -> Found:
    """C6.2.14, .301, .155, .16: a value DecodeBitMasks yields at the width."""
    ok = encode_bitmask(i.imm, i.width) is not None
    return need(ok, Kind.BITMASK, f"{i.imm:#x} is no logical immediate at {i.width} bits")


def logical(i: LogicalShifted) -> Found:
    """The logical (shifted register) pages: any shift, the amount below the width."""
    return need(below(i.amount, i.width), Kind.SHIFT_AMOUNT, f"#{i.amount} at {i.width} bits")


def move_wide(i: MoveWide) -> Found:
    """C6.2.284, .285, .283: imm16 in [0, 65535], hw below width / 16."""
    ok = below(i.imm16, 1 << 16) and below(i.hw, i.width // 16)
    return need(ok, Kind.MOVE_WIDE, f"#{i.imm16}, hw {i.hw} at {i.width} bits")


def bitfield(i: Bitfield) -> Found:
    """C6.2.355, .39, .487: immr and imms below the width."""
    ok = below(i.immr, i.width) and below(i.imms, i.width)
    return need(ok, Kind.BITFIELD, f"#{i.immr}, #{i.imms} at {i.width} bits")


def extract(i: Extract) -> Found:
    """C6.2.160: lsb below the width."""
    return need(below(i.lsb, i.width), Kind.BITFIELD, f"#{i.lsb} at {i.width} bits")


def tested_bit(i: TestBranch) -> Found:
    """C6.2.479, .478: b5:b40, a bit in [0, 63]; there is no width field."""
    return need(below(i.bit, 64), Kind.BITFIELD, f"#{i.bit} is not in [0, 63]")


def cond_compare_reg(i: CondCompareReg) -> Found:
    """C6.2.80, .82: nzcv in [0, 15]."""
    return need(below(i.nzcv, 16), Kind.COND_IMM, f"nzcv #{i.nzcv} is not in [0, 15]")


def cond_compare_imm(i: CondCompareImm) -> Found:
    """C6.2.79, .81: imm5 in [0, 31], nzcv in [0, 15]."""
    ok = below(i.imm5, 32) and below(i.nzcv, 16)
    return need(ok, Kind.COND_IMM, f"#{i.imm5}, #{i.nzcv} out of [0, 31], [0, 15]")


def data_proc1(i: DataProc1) -> Found:
    """C6.2.344: REV32 has no 32-bit form."""
    ok = not (i.op is OpDataProc1.REV32 and i.width is Width.W32)
    return need(ok, Kind.WIDTH, "rev32 is 64-bit only")


def scaled(offset: int, size: int, units: range) -> bool:
    """Whether `offset` is `size` times one of `units`."""
    return offset % size == 0 and offset // size in units


# The register-offset options a load or store encodes (option<1> set; C6.2.218 and siblings).
OPTIONS = frozenset({Extend.UXTW, Extend.UXTX, Extend.SXTW, Extend.SXTX})


def address(addr: Offset | PreIndex | PostIndex | RegOffset, size: int) -> Found:
    """An unsigned offset a multiple of the size below 4096 of them; a pre- or post-index
    offset a simm9; a register offset's option one of the four the encoding has."""
    match addr:
        case Offset(imm=imm):
            ok = scaled(imm, size, range(4096))
            return need(ok, Kind.OFFSET, f"#{imm} is not {size} times [0, 4095]")
        case PreIndex(imm=imm) | PostIndex(imm=imm):
            return need(-256 <= imm <= 255, Kind.OFFSET, f"#{imm} is not in [-256, 255]")
        case RegOffset(option=option):
            return need(option in OPTIONS, Kind.EXTEND_AMOUNT, f"{option} is no index option")
        case _:
            assert_never(addr)


def writeback_base(rt: Reg, addr: object) -> bool:
    """Whether a pre- or post-index writes back onto the transfer register (K1.2.17.10-.15,
    .24-.26); sp is never a transfer register, since rt names the zero register there."""
    return isinstance(addr, PreIndex | PostIndex) and addr.rn is rt and rt is not Reg.SP


def load_store(i: LoadStore) -> Found:
    """The addressing mode's range, and no writeback onto rt."""
    overlap = need(not writeback_base(i.rt, i.addr), Kind.UNPREDICTABLE, "writeback base is rt")
    return address(i.addr, i.op.size) + overlap


def unscaled(i: LoadStoreUnscaled) -> Found:
    """C6.2.446-.448, .259-.264: simm9."""
    return need(-256 <= i.simm9 <= 255, Kind.OFFSET, f"#{i.simm9} is not in [-256, 255]")


def pair(i: Pair) -> Found:
    """C6.2.414, .214, .215: LDPSW 64-bit only; imm7 times the access size; no writeback
    onto rt or rt2 (K1.2.17.7, .9, .19) and no load into one register twice (.7, .9)."""
    size = 4 if i.op is OpPair.LDPSW else i.width // 8
    width = need(i.op is not OpPair.LDPSW or i.width is Width.W64, Kind.WIDTH, "ldpsw is 64-bit")
    offset = need(scaled(i.imm, size, range(-64, 64)), Kind.OFFSET, f"#{i.imm} is not imm7")
    base = i.mode is not Mode.OFFSET and i.rn in (i.rt, i.rt2) and i.rn is not Reg.SP
    twice = i.op is not OpPair.STP and i.rt is i.rt2
    fine = not (base or twice)
    return width + offset + need(fine, Kind.UNPREDICTABLE, "writeback base or rt2 is rt")


type Operand = Callable[[Any], Found]
OPERANDS: dict[type, Operand] = {
    AddSubImm: add_sub_imm,
    AddSubShifted: add_sub_shifted,
    AddSubExtended: add_sub_extended,
    LogicalImm: logical_imm,
    LogicalShifted: logical,
    MoveWide: move_wide,
    Bitfield: bitfield,
    Extract: extract,
    TestBranch: tested_bit,
    CondCompareReg: cond_compare_reg,
    CondCompareImm: cond_compare_imm,
    DataProc1: data_proc1,
    LoadStore: load_store,
    LoadStoreUnscaled: unscaled,
    Pair: pair,
}

# The slots where register 31 is sp (C6.1.3), by the class that holds them; every other
# register slot names the zero register. The flag-setting forms write the zero register.
SP_SLOTS: dict[type, frozenset[str]] = {
    AddSubImm: frozenset({"rd", "rn"}),
    AddSubExtended: frozenset({"rd", "rn"}),
    LogicalImm: frozenset({"rd"}),
    LoadStoreUnscaled: frozenset({"rn"}),
    Pair: frozenset({"rn"}),
    Offset: frozenset({"rn"}),
    PreIndex: frozenset({"rn"}),
    PostIndex: frozenset({"rn"}),
    RegOffset: frozenset({"rn"}),
}
FLAGS = frozenset({OpAddSub.ADDS, OpAddSub.SUBS, OpLogicalImm.ANDS})


def admitted(owner: object, slot: str) -> Reg:
    """The register 31 means in `owner`'s `slot`: SP or ZR."""
    flags = slot == "rd" and getattr(owner, "op", None) in FLAGS
    sp = slot in SP_SLOTS.get(type(owner), frozenset()) and not flags
    return Reg.SP if sp else Reg.ZR


def slots(value: object) -> Iterator[tuple[object, str, Reg]]:
    """Every register slot of `value` and the dataclasses inside it: owner, name, register."""
    for field in fields(value) if is_dataclass(value) else ():
        held = getattr(value, field.name)
        if isinstance(held, Reg):
            yield value, field.name, held
        else:
            yield from slots(held)


def register31(instr: Instr) -> Found:
    """sp or the zero register only in a slot whose register 31 is that one."""
    return tuple(
        (Kind.REG31, f"{slot} is {reg.name.lower()}")
        for owner, slot, reg in slots(instr)
        if reg in (Reg.SP, Reg.ZR) and reg is not admitted(owner, slot)
    )


# Branch reach by class: an offset in [-2^k, 2^k - 4] bytes (C6.2.479, .34, .78, .12, .35).
REACH: dict[type, int] = {TestBranch: 15, BranchCond: 20, CompareBranch: 20, Adr: 20, Branch: 27}
NAME = re.compile(r"\.L[A-Za-z0-9_]+")


def reaches(cls: type, offset: int) -> bool:
    """Whether a `cls` transfer reaches `offset` bytes."""
    return -(1 << REACH[cls]) <= offset <= (1 << REACH[cls]) - 4


def addresses(program: Program) -> dict[str, int]:
    """Each label's first definition: the byte address of the next instruction."""
    found: dict[str, int] = {}
    count = 0
    for item in program:
        if isinstance(item, Label):
            found.setdefault(item.name, 4 * count)
        else:
            count += 1
    return found


def target(item: object, at: int, labels: dict[str, int]) -> Found:
    """A branch or adr: its label well named and, when defined, within reach."""
    held = getattr(item, "target", None)
    if not isinstance(held, Label):
        return ()
    named = need(NAME.fullmatch(held.name) is not None, Kind.LABEL_NAME, held.name)
    offset = labels.get(held.name, at) - at
    return named + need(reaches(type(item), offset), Kind.BRANCH_RANGE, f"{offset} bytes")


def definition(label: Label, seen: set[str]) -> Found:
    """A label's name `.L`-local, and not defined before."""
    named = need(NAME.fullmatch(label.name) is not None, Kind.LABEL_NAME, label.name)
    return named + need(label.name not in seen, Kind.DUPLICATE_LABEL, label.name)


def undefined(program: Program, labels: dict[str, int]) -> tuple[Problem, ...]:
    """One program problem per label referenced and never defined, in reference order."""
    missing = dict.fromkeys(
        held.name
        for item in program
        if isinstance(held := getattr(item, "target", None), Label) and held.name not in labels
    )
    return tuple(Problem(None, Kind.UNDEFINED_LABEL, name) for name in missing)


def nothing(_: object) -> Found:
    """No operand ranges: the classes whose fields hold only registers and labels."""
    return ()


def instruction(instr: Instr, at: int, labels: dict[str, int]) -> Found:
    """Every violation of one instruction at byte address `at`."""
    ranges = OPERANDS.get(type(instr), nothing)(instr)
    return ranges + register31(instr) + target(instr, at, labels)


def check(program: Program) -> tuple[Problem, ...]:
    """Every problem of `program`: the items' in order, then the undefined labels'."""
    labels = addresses(program)
    seen: set[str] = set()
    found: list[Problem] = []
    count = 0
    for index, item in enumerate(program):
        if isinstance(item, Label):
            problems = definition(item, seen)
            seen.add(item.name)
        else:
            problems = instruction(item, 4 * count, labels)
            count += 1
        found += (Problem(index, kind, detail) for kind, detail in problems)
    return (*found, *undefined(program, labels))
