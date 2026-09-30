"""The model against C6.2 (DDI 0487 M.d): the listing law, and register names by width."""

from dataclasses import fields
from enum import StrEnum
from typing import get_args

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fpl.asm.aarch64 import model
from fpl.asm.aarch64.model import (
    Cond,
    Extend,
    Instr,
    LoadStore,
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
    Reg,
    Width,
)

# The 105 base-instruction pages of the subset, copied from M.d's table of contents: section,
# title, the model class, the addressing family (LoadStore only), and the ops on that page.
# fmt: off
TABLE = [
    ("C6.2.5", "ADD (immediate)", "AddSubImm", "", (OpAddSub.ADD,)),
    ("C6.2.10", "ADDS (immediate)", "AddSubImm", "", (OpAddSub.ADDS,)),
    ("C6.2.457", "SUB (immediate)", "AddSubImm", "", (OpAddSub.SUB,)),
    ("C6.2.464", "SUBS (immediate)", "AddSubImm", "", (OpAddSub.SUBS,)),
    ("C6.2.6", "ADD (shifted register)", "AddSubShifted", "", (OpAddSub.ADD,)),
    ("C6.2.11", "ADDS (shifted register)", "AddSubShifted", "", (OpAddSub.ADDS,)),
    ("C6.2.458", "SUB (shifted register)", "AddSubShifted", "", (OpAddSub.SUB,)),
    ("C6.2.465", "SUBS (shifted register)", "AddSubShifted", "", (OpAddSub.SUBS,)),
    ("C6.2.4", "ADD (extended register)", "AddSubExtended", "", (OpAddSub.ADD,)),
    ("C6.2.9", "ADDS (extended register)", "AddSubExtended", "", (OpAddSub.ADDS,)),
    ("C6.2.456", "SUB (extended register)", "AddSubExtended", "", (OpAddSub.SUB,)),
    ("C6.2.463", "SUBS (extended register)", "AddSubExtended", "", (OpAddSub.SUBS,)),
    ("C6.2.2", "ADC", "AddSubCarry", "", (OpAddSubCarry.ADC,)),
    ("C6.2.3", "ADCS", "AddSubCarry", "", (OpAddSubCarry.ADCS,)),
    ("C6.2.352", "SBC", "AddSubCarry", "", (OpAddSubCarry.SBC,)),
    ("C6.2.353", "SBCS", "AddSubCarry", "", (OpAddSubCarry.SBCS,)),
    ("C6.2.14", "AND (immediate)", "LogicalImm", "", (OpLogicalImm.AND,)),
    ("C6.2.301", "ORR (immediate)", "LogicalImm", "", (OpLogicalImm.ORR,)),
    ("C6.2.155", "EOR (immediate)", "LogicalImm", "", (OpLogicalImm.EOR,)),
    ("C6.2.16", "ANDS (immediate)", "LogicalImm", "", (OpLogicalImm.ANDS,)),
    ("C6.2.15", "AND (shifted register)", "LogicalShifted", "", (OpLogical.AND,)),
    ("C6.2.41", "BIC (shifted register)", "LogicalShifted", "", (OpLogical.BIC,)),
    ("C6.2.302", "ORR (shifted register)", "LogicalShifted", "", (OpLogical.ORR,)),
    ("C6.2.300", "ORN (shifted register)", "LogicalShifted", "", (OpLogical.ORN,)),
    ("C6.2.156", "EOR (shifted register)", "LogicalShifted", "", (OpLogical.EOR,)),
    ("C6.2.154", "EON (shifted register)", "LogicalShifted", "", (OpLogical.EON,)),
    ("C6.2.17", "ANDS (shifted register)", "LogicalShifted", "", (OpLogical.ANDS,)),
    ("C6.2.42", "BICS (shifted register)", "LogicalShifted", "", (OpLogical.BICS,)),
    ("C6.2.284", "MOVN", "MoveWide", "", (OpMoveWide.MOVN,)),
    ("C6.2.285", "MOVZ", "MoveWide", "", (OpMoveWide.MOVZ,)),
    ("C6.2.283", "MOVK", "MoveWide", "", (OpMoveWide.MOVK,)),
    ("C6.2.355", "SBFM", "Bitfield", "", (OpBitfield.SBFM,)),
    ("C6.2.39", "BFM", "Bitfield", "", (OpBitfield.BFM,)),
    ("C6.2.487", "UBFM", "Bitfield", "", (OpBitfield.UBFM,)),
    ("C6.2.160", "EXTR", "Extract", "", ('extr',)),
    ("C6.2.12", "ADR", "Adr", "", ('adr',)),
    ("C6.2.271", "LSLV", "DataProc2", "", (OpDataProc2.LSLV,)),
    ("C6.2.274", "LSRV", "DataProc2", "", (OpDataProc2.LSRV,)),
    ("C6.2.21", "ASRV", "DataProc2", "", (OpDataProc2.ASRV,)),
    ("C6.2.349", "RORV", "DataProc2", "", (OpDataProc2.RORV,)),
    ("C6.2.357", "SDIV (quotient)", "DataProc2", "", (OpDataProc2.SDIV,)),
    ("C6.2.490", "UDIV (quotient)", "DataProc2", "", (OpDataProc2.UDIV,)),
    ("C6.2.321", "RBIT", "DataProc1", "", (OpDataProc1.RBIT,)),
    ("C6.2.343", "REV16", "DataProc1", "", (OpDataProc1.REV16,)),
    ("C6.2.342", "REV", "DataProc1", "", (OpDataProc1.REV,)),
    ("C6.2.344", "REV32", "DataProc1", "", (OpDataProc1.REV32,)),
    ("C6.2.91", "CLZ", "DataProc1", "", (OpDataProc1.CLZ,)),
    ("C6.2.90", "CLS", "DataProc1", "", (OpDataProc1.CLS,)),
    ("C6.2.275", "MADD", "MulAdd", "", (OpMulAdd.MADD,)),
    ("C6.2.291", "MSUB", "MulAdd", "", (OpMulAdd.MSUB,)),
    ("C6.2.369", "SMADDL", "MulLong", "", (OpMulLong.SMADDL,)),
    ("C6.2.378", "SMSUBL", "MulLong", "", (OpMulLong.SMSUBL,)),
    ("C6.2.491", "UMADDL", "MulLong", "", (OpMulLong.UMADDL,)),
    ("C6.2.497", "UMSUBL", "MulLong", "", (OpMulLong.UMSUBL,)),
    ("C6.2.379", "SMULH", "MulHigh", "", (OpMulHigh.SMULH,)),
    ("C6.2.498", "UMULH", "MulHigh", "", (OpMulHigh.UMULH,)),
    ("C6.2.138", "CSEL", "CondSelect", "", (OpCondSelect.CSEL,)),
    ("C6.2.141", "CSINC", "CondSelect", "", (OpCondSelect.CSINC,)),
    ("C6.2.142", "CSINV", "CondSelect", "", (OpCondSelect.CSINV,)),
    ("C6.2.143", "CSNEG", "CondSelect", "", (OpCondSelect.CSNEG,)),
    ("C6.2.80", "CCMN (register)", "CondCompareReg", "", (OpCondCompare.CCMN,)),
    ("C6.2.82", "CCMP (register)", "CondCompareReg", "", (OpCondCompare.CCMP,)),
    ("C6.2.79", "CCMN (immediate)", "CondCompareImm", "", (OpCondCompare.CCMN,)),
    ("C6.2.81", "CCMP (immediate)", "CondCompareImm", "", (OpCondCompare.CCMP,)),
    ("C6.2.35", "B", "Branch", "", (OpBranch.B,)),
    ("C6.2.43", "BL", "Branch", "", (OpBranch.BL,)),
    ("C6.2.34", "B.cond", "BranchCond", "", ('b.',)),
    ("C6.2.78", "CBZ", "CompareBranch", "", (OpCompareBranch.CBZ,)),
    ("C6.2.77", "CBNZ", "CompareBranch", "", (OpCompareBranch.CBNZ,)),
    ("C6.2.479", "TBZ", "TestBranch", "", (OpTestBranch.TBZ,)),
    ("C6.2.478", "TBNZ", "TestBranch", "", (OpTestBranch.TBNZ,)),
    ("C6.2.46", "BR", "BranchReg", "", (OpBranchReg.BR,)),
    ("C6.2.44", "BLR", "BranchReg", "", (OpBranchReg.BLR,)),
    ("C6.2.338", "RET", "BranchReg", "", (OpBranchReg.RET,)),
    ("C6.2.299", "NOP", "Nop", "", ('nop',)),
    ("C6.2.417", "STRB (immediate)", "LoadStore", "immediate", (OpLoadStore.STRB,)),
    ("C6.2.220", "LDRB (immediate)", "LoadStore", "immediate", (OpLoadStore.LDRB,)),
    ("C6.2.224", "LDRSB (immediate)", "LoadStore", "immediate",
     (OpLoadStore.LDRSB_W, OpLoadStore.LDRSB_X)),
    ("C6.2.419", "STRH (immediate)", "LoadStore", "immediate", (OpLoadStore.STRH,)),
    ("C6.2.222", "LDRH (immediate)", "LoadStore", "immediate", (OpLoadStore.LDRH,)),
    ("C6.2.226", "LDRSH (immediate)", "LoadStore", "immediate",
     (OpLoadStore.LDRSH_W, OpLoadStore.LDRSH_X)),
    ("C6.2.415", "STR (immediate)", "LoadStore", "immediate",
     (OpLoadStore.STR_W, OpLoadStore.STR_X)),
    ("C6.2.216", "LDR (immediate)", "LoadStore", "immediate",
     (OpLoadStore.LDR_W, OpLoadStore.LDR_X)),
    ("C6.2.228", "LDRSW (immediate)", "LoadStore", "immediate", (OpLoadStore.LDRSW,)),
    ("C6.2.418", "STRB (register)", "LoadStore", "register", (OpLoadStore.STRB,)),
    ("C6.2.221", "LDRB (register)", "LoadStore", "register", (OpLoadStore.LDRB,)),
    ("C6.2.225", "LDRSB (register)", "LoadStore", "register",
     (OpLoadStore.LDRSB_W, OpLoadStore.LDRSB_X)),
    ("C6.2.420", "STRH (register)", "LoadStore", "register", (OpLoadStore.STRH,)),
    ("C6.2.223", "LDRH (register)", "LoadStore", "register", (OpLoadStore.LDRH,)),
    ("C6.2.227", "LDRSH (register)", "LoadStore", "register",
     (OpLoadStore.LDRSH_W, OpLoadStore.LDRSH_X)),
    ("C6.2.416", "STR (register)", "LoadStore", "register", (OpLoadStore.STR_W, OpLoadStore.STR_X)),
    ("C6.2.218", "LDR (register)", "LoadStore", "register", (OpLoadStore.LDR_W, OpLoadStore.LDR_X)),
    ("C6.2.230", "LDRSW (register)", "LoadStore", "register", (OpLoadStore.LDRSW,)),
    ("C6.2.447", "STURB", "LoadStoreUnscaled", "", (OpLoadStoreUnscaled.STURB,)),
    ("C6.2.448", "STURH", "LoadStoreUnscaled", "", (OpLoadStoreUnscaled.STURH,)),
    ("C6.2.446", "STUR", "LoadStoreUnscaled", "",
     (OpLoadStoreUnscaled.STUR_W, OpLoadStoreUnscaled.STUR_X)),
    ("C6.2.260", "LDURB", "LoadStoreUnscaled", "", (OpLoadStoreUnscaled.LDURB,)),
    ("C6.2.261", "LDURH", "LoadStoreUnscaled", "", (OpLoadStoreUnscaled.LDURH,)),
    ("C6.2.262", "LDURSB", "LoadStoreUnscaled", "",
     (OpLoadStoreUnscaled.LDURSB_W, OpLoadStoreUnscaled.LDURSB_X)),
    ("C6.2.263", "LDURSH", "LoadStoreUnscaled", "",
     (OpLoadStoreUnscaled.LDURSH_W, OpLoadStoreUnscaled.LDURSH_X)),
    ("C6.2.259", "LDUR", "LoadStoreUnscaled", "",
     (OpLoadStoreUnscaled.LDUR_W, OpLoadStoreUnscaled.LDUR_X)),
    ("C6.2.264", "LDURSW", "LoadStoreUnscaled", "", (OpLoadStoreUnscaled.LDURSW,)),
    ("C6.2.414", "STP", "Pair", "", (OpPair.STP,)),
    ("C6.2.214", "LDP", "Pair", "", (OpPair.LDP,)),
    ("C6.2.215", "LDPSW", "Pair", "", (OpPair.LDPSW,)),
]
# fmt: on
# The pages that hold two triples: one page, the W and X forms as two ops.
FIBRES = {
    "LDRSB (immediate)",
    "LDRSH (immediate)",
    "STR (immediate)",
    "LDR (immediate)",
    "LDRSB (register)",
    "LDRSH (register)",
    "STR (register)",
    "LDR (register)",
    "LDURSB",
    "LDURSH",
    "STUR",
    "LDUR",
}
# The alias pages C6.2 lists for these bases (C1.4): text, never a construct.
ALIASES = {
    "ASR",
    "BFC",
    "BFI",
    "BFXIL",
    "CINC",
    "CINV",
    "CMN",
    "CMP",
    "CNEG",
    "CSET",
    "CSETM",
    "LSL",
    "LSR",
    "MNEG",
    "MOV",
    "MUL",
    "MVN",
    "NEG",
    "NEGS",
    "NGC",
    "NGCS",
    "ROR",
    "SBFIZ",
    "SBFX",
    "SMNEGL",
    "SMULL",
    "SXTB",
    "SXTH",
    "SXTW",
    "TST",
    "UBFIZ",
    "UBFX",
    "UMNEGL",
    "UMULL",
    "UXTB",
    "UXTH",
}
type Triple = tuple[str, str, str]


def ops(cls: type) -> list[str]:
    """The op values of a class: its op enum's, or its one mnemonic."""
    kinds = {field.name: field.type for field in fields(cls)}
    op = kinds.get("op")
    if isinstance(op, type) and issubclass(op, StrEnum):
        return [member.value for member in op]
    mnemonic = str(vars(cls)["MNEMONIC"])
    return [mnemonic]


def triples() -> list[Triple]:
    """The model's (class, op, addressing family) triples; only LoadStore has two families."""
    families = {LoadStore: ("immediate", "register")}
    return [
        (cls.__name__, op, family)
        for cls in get_args(Instr.__value__)
        for family in families.get(cls, ("",))
        for op in ops(cls)
    ]


PAGE = {
    (cls, op, family): (section, title) for section, title, cls, family, on in TABLE for op in on
}


@given(st.sampled_from(TABLE))
def test_the_triples_map_onto_the_105_pages(
    row: tuple[str, str, str, str, tuple[str, ...]],
) -> None:
    """[law: listing-one-to-one] The map from the model's triples to C6.2 pages is total and
    onto the 105 pages of the table, with no alias page among them; every page has one triple
    except the twelve of FIBRES, which have two. 117 triples, 105 pages."""
    section, title, *_ = row
    model_triples = triples()
    assert len(model_triples) == len(set(model_triples)) == 117
    assert set(PAGE) == set(model_triples)
    assert len(set(PAGE.values())) == len(TABLE) == 105
    assert not {title.split(" ")[0] for _, title, *_ in TABLE} & ALIASES
    fibre = [triple for triple, page in PAGE.items() if page == (section, title)]
    assert len(fibre) == (2 if title in FIBRES else 1), fibre
    assert all(getattr(model, cls) for cls, _, _ in fibre)


# fmt: off
NAMES = [
    (Reg.X0, "x0"), (Reg.X1, "x1"), (Reg.X2, "x2"), (Reg.X3, "x3"), (Reg.X4, "x4"),
    (Reg.X5, "x5"), (Reg.X6, "x6"), (Reg.X7, "x7"), (Reg.X8, "x8"), (Reg.X9, "x9"),
    (Reg.X10, "x10"), (Reg.X11, "x11"), (Reg.X12, "x12"), (Reg.X13, "x13"), (Reg.X14, "x14"),
    (Reg.X15, "x15"), (Reg.X16, "x16"), (Reg.X17, "x17"), (Reg.X18, "x18"), (Reg.X19, "x19"),
    (Reg.X20, "x20"), (Reg.X21, "x21"), (Reg.X22, "x22"), (Reg.X23, "x23"), (Reg.X24, "x24"),
    (Reg.X25, "x25"), (Reg.X26, "x26"), (Reg.X27, "x27"), (Reg.X28, "x28"), (Reg.X29, "x29"),
    (Reg.X30, "x30"), (Reg.SP, "sp"), (Reg.ZR, "xzr"),
]
# fmt: on
# fmt: off
# C1.2.4: each condition by its encoding, with llvm-objdump's names (hs, lo for cs, cc).
CONDS = [
    (Cond.EQ, 0b0000, "eq"), (Cond.NE, 0b0001, "ne"), (Cond.HS, 0b0010, "hs"),
    (Cond.LO, 0b0011, "lo"), (Cond.MI, 0b0100, "mi"), (Cond.PL, 0b0101, "pl"),
    (Cond.VS, 0b0110, "vs"), (Cond.VC, 0b0111, "vc"), (Cond.HI, 0b1000, "hi"),
    (Cond.LS, 0b1001, "ls"), (Cond.GE, 0b1010, "ge"), (Cond.LT, 0b1011, "lt"),
    (Cond.GT, 0b1100, "gt"), (Cond.LE, 0b1101, "le"), (Cond.AL, 0b1110, "al"),
    (Cond.NV, 0b1111, "nv"),
]
# C6.2.4, the option field: the eight extends as printed.
EXTENDS = [
    (Extend.UXTB, "uxtb"), (Extend.UXTH, "uxth"), (Extend.UXTW, "uxtw"), (Extend.UXTX, "uxtx"),
    (Extend.SXTB, "sxtb"), (Extend.SXTH, "sxth"), (Extend.SXTW, "sxtw"), (Extend.SXTX, "sxtx"),
]
# fmt: on


def test_the_conditions_are_c1_2_4s_encodings_and_names() -> None:
    assert [(int(cond), cond.text) for cond, *_ in CONDS] == [row[1:] for row in CONDS]
    assert [cond for cond, *_ in CONDS] == list(Cond)


def test_the_extends_are_named() -> None:
    assert [(ext, ext.value) for ext, _ in EXTENDS] == EXTENDS
    assert [ext for ext, _ in EXTENDS] == list(Extend)


def test_every_register_is_named() -> None:
    assert sorted(reg for reg, _ in NAMES) == list(Reg)


@pytest.mark.parametrize(("reg", "name"), NAMES)
def test_the_x_names(reg: Reg, name: str) -> None:
    assert reg.name_at(Width.W64) == name


@given(st.sampled_from(Reg))
def test_a_w_name_is_its_x_name_with_w(reg: Reg) -> None:
    """The 32-bit view renames x to w, sp to wsp and xzr to wzr."""
    x = reg.name_at(Width.W64)
    assert reg.name_at(Width.W32) == ("wsp" if x == "sp" else "w" + x[1:])
