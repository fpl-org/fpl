"""The alias rows against their C6.2 conditions, restated here from the pages: which alias
the spec prefers for a drawn instruction of each class, and the texts of MOV and MUL."""

import re
from collections.abc import Callable
from typing import Any

import pytest
from aarch64_strategies import BY_CLASS, fresh_tables, witnesses
from hypothesis import given
from hypothesis import strategies as st

from fpl.asm.aarch64.alias import Row, decode_bitmask, encodings, fired, preferred, rows
from fpl.asm.aarch64.model import (
    AddSubCarry,
    AddSubExtended,
    AddSubImm,
    AddSubShifted,
    Bitfield,
    Cond,
    CondSelect,
    DataProc2,
    Extract,
    Instr,
    Label,
    LogicalImm,
    LogicalShifted,
    MoveWide,
    MulAdd,
    MulLong,
    OpAddSub,
    OpAddSubCarry,
    OpBitfield,
    OpCondSelect,
    OpDataProc2,
    OpLogical,
    OpLogicalImm,
    OpMoveWide,
    OpMulAdd,
    OpMulLong,
    Reg,
    Shift,
    Width,
)

regs = st.sampled_from(Reg)
widths = st.sampled_from(Width)
# One past each end of the encodable ranges, so the out-of-range side is drawn too.
imm16s, hws = st.integers(-1, 0x10000), st.integers(-1, 4)
move_wides = st.builds(
    MoveWide, st.sampled_from([OpMoveWide.MOVZ, OpMoveWide.MOVK]), widths, regs, imm16s, hws
)
mul_adds = st.builds(MulAdd, st.just(OpMulAdd.MADD), widths, regs, regs, regs, regs)


@given(move_wides)
def test_mov_is_preferred_exactly_when_movz_moves_a_nonzero_chunk_or_zero(i: MoveWide) -> None:
    """MOVZ page: MOV (wide immediate) when !(IsZero(imm16) && hw != '00'), fields in range;
    its immediate is the value moved, signed at the width."""
    mnemonic, operands = preferred(i)
    encodable = 0 <= i.imm16 <= 0xFFFF and 0 <= i.hw < i.width // 16
    alias = i.op is OpMoveWide.MOVZ and encodable and not (i.imm16 == 0 and i.hw != 0)
    assert (mnemonic == "mov") == alias
    if alias:
        value = int(operands.rsplit("#", 1)[1])
        assert -(1 << (i.width - 1)) <= value < 1 << (i.width - 1)
        assert value % (1 << i.width) == i.imm16 << (16 * i.hw)
    else:
        assert (mnemonic, operands) == (i.op.value, i.operands())


@given(mul_adds)
def test_mul_is_preferred_exactly_when_madd_accumulates_zero(i: MulAdd) -> None:
    """MADD page: MUL when Ra == '11111'; it prints the three other registers."""
    mnemonic, operands = preferred(i)
    assert (mnemonic == "mul") == (i.op is OpMulAdd.MADD and i.ra is Reg.ZR)
    names = [r.name_at(i.width) for r in (i.rd, i.rn, i.rm, i.ra)]
    assert operands == ", ".join(names[:3] if mnemonic == "mul" else names)


@pytest.mark.parametrize(
    ("instr", "text"),
    [
        (MoveWide(OpMoveWide.MOVZ, Width.W64, Reg.X0, 6, 0), ("mov", "x0, #6")),
        (MoveWide(OpMoveWide.MOVZ, Width.W64, Reg.X1, 0, 1), ("movz", "x1, #0, lsl #16")),
        (MoveWide(OpMoveWide.MOVZ, Width.W32, Reg.X1, 0xFFFF, 1), ("mov", "w1, #-65536")),
        (
            MoveWide(OpMoveWide.MOVZ, Width.W64, Reg.X1, 0xFFFF, 3),
            ("mov", "x1, #-281474976710656"),
        ),
        (MoveWide(OpMoveWide.MOVZ, Width.W64, Reg.X1, 1, 2), ("mov", "x1, #4294967296")),
        (MoveWide(OpMoveWide.MOVZ, Width.W64, Reg.X1, 0x10000, 0), ("movz", "x1, #65536")),
        (MoveWide(OpMoveWide.MOVZ, Width.W32, Reg.ZR, 1, 2), ("movz", "wzr, #1, lsl #32")),
        (MoveWide(OpMoveWide.MOVN, Width.W32, Reg.X1, 0xFFFF, 0), ("movn", "w1, #65535")),
        (MoveWide(OpMoveWide.MOVK, Width.W64, Reg.X1, 1, 1), ("movk", "x1, #1, lsl #16")),
        (MulAdd(OpMulAdd.MADD, Width.W64, Reg.X0, Reg.X0, Reg.X1, Reg.ZR), ("mul", "x0, x0, x1")),
        (
            MulAdd(OpMulAdd.MADD, Width.W32, Reg.X1, Reg.X2, Reg.X3, Reg.X4),
            ("madd", "w1, w2, w3, w4"),
        ),
        (
            MulAdd(OpMulAdd.MSUB, Width.W64, Reg.SP, Reg.X30, Reg.ZR, Reg.X4),
            ("msub", "sp, x30, xzr, x4"),
        ),
        (
            MulAdd(OpMulAdd.MSUB, Width.W32, Reg.SP, Reg.X30, Reg.ZR, Reg.X4),
            ("msub", "wsp, w30, wzr, w4"),
        ),
    ],
)
def test_probe_texts(instr: MoveWide | MulAdd, text: tuple[str, str]) -> None:
    """Texts llvm-objdump printed in the design's probe, and register names at both widths."""
    assert preferred(instr) == text


# The spec's alias conditions, one per row that is not `spec_differs`, in the order the rows
# are tried: (page, alias) and the condition over the fields as the page names them. Register
# 31 is SP in the slots of ADD (immediate) and ZR elsewhere; cond == '111x' is AL or NV. The
# two divergent rows (BFM's BFC, ORR's MOV) are left out: their conditions overlap no later
# row of their class, so leaving them out moves no other row.
type Condition = Callable[[Any], bool]
ZR, SP = Reg.ZR, Reg.SP
ALWAYS = (Cond.AL, Cond.NV)


def top(i: Any) -> int:
    """sf:'11111', the largest field value at the width."""
    return int(i.width) - 1


def bfx_preferred(i: Bitfield) -> bool:
    """BFXPreferred(sf, uns, imms, immr) (J1.2): not UBFIZ/SBFIZ, not LSR/ASR, not a 32-bit
    UXT[BH] or SXT[BH], not a 64-bit SXT[BHW]."""
    sf, uns = i.width is Width.W64, i.op is OpBitfield.UBFM
    if i.imms < i.immr or i.imms == top(i):
        return False
    if i.immr == 0 and not sf and i.imms in (7, 15):
        return False
    return not (i.immr == 0 and sf and not uns and i.imms in (7, 15, 31))


def rd_zero(op: object) -> Condition:
    """The op, with Rd == '11111' (CMN, CMP, TST)."""
    return lambda i: i.op is op and i.rd is ZR


def rn_zero(op: object) -> Condition:
    """The op, with Rn == '11111' (NEG, NEGS, NGC, NGCS, MVN)."""
    return lambda i: i.op is op and i.rn is ZR


def ra_zero(op: object) -> Condition:
    """The op, with Ra == '11111' (MUL, MNEG and the long forms)."""
    return lambda i: i.op is op and i.ra is ZR


def always(op: object) -> Condition:
    """The op, unconditionally (the variable shifts)."""
    return lambda i: i.op is op


def moved(i: MoveWide) -> bool:
    """!(IsZero(imm16) && hw != '00')."""
    return not (i.imm16 == 0 and i.hw != 0)


def set_by(op: OpCondSelect) -> Condition:
    """CSET, CSETM: Rm == '11111' && cond != '111x' && Rn == '11111'."""
    return lambda i: i.op is op and i.rm is ZR and i.cond not in ALWAYS and i.rn is ZR


def once(op: OpCondSelect) -> Condition:
    """CINC, CINV: Rm != '11111' && cond != '111x' && Rn != '11111' && Rn == Rm."""
    return lambda i: i.op is op and i.rm is not ZR and i.cond not in ALWAYS and i.rn is i.rm


def field(op: OpBitfield, immr: int, imms: int, width: Width | None = None) -> Condition:
    """The op with immr and imms fixed, at `width` if the alias fixes sf (SXTW, UXTB, UXTH)."""
    return lambda i: i.op is op and i.immr == immr and i.imms == imms and width in (None, i.width)


SBFM, BFM, UBFM = OpBitfield.SBFM, OpBitfield.BFM, OpBitfield.UBFM
SPEC: dict[type, tuple[tuple[tuple[str, str], Condition], ...]] = {
    MoveWide: (
        (("C6.2.285", "MOV"), lambda i: i.op is OpMoveWide.MOVZ and moved(i)),
        (
            ("C6.2.284", "MOV"),
            lambda i: (
                i.op is OpMoveWide.MOVN
                and moved(i)
                and not (i.width is Width.W32 and i.imm16 == 0xFFFF)
            ),
        ),
    ),
    LogicalImm: ((("C6.2.16", "TST"), rd_zero(OpLogicalImm.ANDS)),),
    AddSubImm: (
        (
            ("C6.2.5", "MOV"),
            lambda i: i.op is OpAddSub.ADD and not i.lsl12 and i.imm == 0 and SP in (i.rd, i.rn),
        ),
        (("C6.2.10", "CMN"), rd_zero(OpAddSub.ADDS)),
        (("C6.2.464", "CMP"), rd_zero(OpAddSub.SUBS)),
    ),
    LogicalShifted: (
        (
            ("C6.2.302", "MOV"),
            lambda i: rn_zero(OpLogical.ORR)(i) and i.shift is Shift.LSL and i.amount == 0,
        ),
        (("C6.2.300", "MVN"), rn_zero(OpLogical.ORN)),
        (("C6.2.17", "TST"), rd_zero(OpLogical.ANDS)),
    ),
    AddSubExtended: (
        (("C6.2.9", "CMN"), rd_zero(OpAddSub.ADDS)),
        (("C6.2.463", "CMP"), rd_zero(OpAddSub.SUBS)),
    ),
    AddSubShifted: (
        (("C6.2.11", "CMN"), rd_zero(OpAddSub.ADDS)),
        (("C6.2.465", "CMP"), rd_zero(OpAddSub.SUBS)),
        (("C6.2.458", "NEG"), rn_zero(OpAddSub.SUB)),
        (("C6.2.465", "NEGS"), rn_zero(OpAddSub.SUBS)),
    ),
    AddSubCarry: (
        (("C6.2.352", "NGC"), rn_zero(OpAddSubCarry.SBC)),
        (("C6.2.353", "NGCS"), rn_zero(OpAddSubCarry.SBCS)),
    ),
    Bitfield: (
        (("C6.2.355", "ASR"), lambda i: i.op is SBFM and i.imms == top(i)),
        (("C6.2.355", "SBFIZ"), lambda i: i.op is SBFM and i.imms < i.immr),
        (("C6.2.355", "SBFX"), lambda i: i.op is SBFM and bfx_preferred(i)),
        (("C6.2.355", "SXTB"), field(SBFM, 0, 7)),
        (("C6.2.355", "SXTH"), field(SBFM, 0, 15)),
        (("C6.2.355", "SXTW"), field(SBFM, 0, 31, Width.W64)),
        (("C6.2.39", "BFI"), lambda i: i.op is BFM and i.rn is not ZR and i.imms < i.immr),
        (("C6.2.39", "BFXIL"), lambda i: i.op is BFM and i.imms >= i.immr),
        (
            ("C6.2.487", "LSL"),
            lambda i: i.op is UBFM and i.imms != top(i) and i.imms + 1 == i.immr,
        ),
        (("C6.2.487", "LSR"), lambda i: i.op is UBFM and i.imms == top(i)),
        (("C6.2.487", "UBFIZ"), lambda i: i.op is UBFM and i.imms < i.immr),
        (("C6.2.487", "UBFX"), lambda i: i.op is UBFM and bfx_preferred(i)),
        (("C6.2.487", "UXTB"), field(UBFM, 0, 7, Width.W32)),
        (("C6.2.487", "UXTH"), field(UBFM, 0, 15, Width.W32)),
    ),
    Extract: ((("C6.2.160", "ROR"), lambda i: i.rn is i.rm),),
    DataProc2: (
        (("C6.2.271", "LSL"), always(OpDataProc2.LSLV)),
        (("C6.2.274", "LSR"), always(OpDataProc2.LSRV)),
        (("C6.2.21", "ASR"), always(OpDataProc2.ASRV)),
        (("C6.2.349", "ROR"), always(OpDataProc2.RORV)),
    ),
    MulAdd: (
        (("C6.2.275", "MUL"), ra_zero(OpMulAdd.MADD)),
        (("C6.2.291", "MNEG"), ra_zero(OpMulAdd.MSUB)),
    ),
    MulLong: (
        (("C6.2.369", "SMULL"), ra_zero(OpMulLong.SMADDL)),
        (("C6.2.378", "SMNEGL"), ra_zero(OpMulLong.SMSUBL)),
        (("C6.2.491", "UMULL"), ra_zero(OpMulLong.UMADDL)),
        (("C6.2.497", "UMNEGL"), ra_zero(OpMulLong.UMSUBL)),
    ),
    CondSelect: (
        (("C6.2.141", "CSET"), set_by(OpCondSelect.CSINC)),
        (("C6.2.141", "CINC"), once(OpCondSelect.CSINC)),
        (("C6.2.142", "CSETM"), set_by(OpCondSelect.CSINV)),
        (("C6.2.142", "CINV"), once(OpCondSelect.CSINV)),
        (
            ("C6.2.143", "CNEG"),
            lambda i: i.op is OpCondSelect.CSNEG and i.cond not in ALWAYS and i.rn is i.rm,
        ),
    ),
}


def key(row: Row[Any]) -> tuple[str, str]:
    """A row's page and alias, read from its cite: `C6.2.465 SUBS (...), NEGS: ...`."""
    alias = re.match(r"[A-Z]+", row.cite.split(", ", 1)[1])
    assert alias is not None, row.cite
    return row.cite.split(" ", 1)[0], alias.group()


def spec(i: Instr) -> tuple[str, str] | None:
    """The alias the restated conditions prefer for `i`, the first that holds."""
    return next((page for page, holds in SPEC[type(i)] if holds(i)), None)


def agreed(row: Row[Any] | None) -> tuple[str, str] | None:
    """The row's key, None for the base form or a row that follows LLVM, not the spec."""
    return None if row is None or row.spec_differs else key(row)


pytestmark = pytest.mark.usefixtures(fresh_tables.__name__)


@pytest.fixture(scope="module")
def reached() -> list[Instr]:
    """witnesses(), found before the property runs: `find` may not nest in a @given."""
    return [w for w in witnesses() if not isinstance(w, Label)]


@given(i=st.one_of(*(BY_CLASS[cls] for cls in rows.__wrapped__())))
def test_each_alias_row_fires_exactly_when_its_spec_condition_holds(
    reached: list[Instr], i: Instr
) -> None:
    """[law: aliases-per-spec] Every row without spec_differs fires exactly when its C6.2
    condition, restated here, holds, over drawn instructions of its class; every row is
    reached by the strategies (witnesses() draws one per row); the spec_differs rows are
    exactly those alias-divergence names: BFM's BFC (printed bfi) and ORR's MOV."""
    every = [row for group in rows().values() for row in group]
    assert agreed(fired(i)) == spec(i)
    assert [fired(w) for w in reached] == every
    assert all(spec(w) == agreed(row) for w, row in zip(reached, every, strict=True))
    divergent = {key(row) for row in every if row.spec_differs}
    assert divergent == {("C6.2.39", "BFC"), ("C6.2.301", "MOV")}
    assert {page for pages in SPEC.values() for page, _ in pages} == {
        key(row) for row in every if not row.spec_differs
    }


@pytest.mark.parametrize(
    ("width", "count", "known"),
    [
        (
            Width.W32,
            1302,
            {1: (0, 0, 0), 0x55555555: (0, 0, 60), 0xFFFEFFFF: (0, 15, 30), 0x00FF00FF: (0, 0, 39)},
        ),
        (
            Width.W64,
            5334,
            {
                1: (1, 0, 0),
                0x5555555555555555: (0, 0, 60),
                0xFFFFFFFFFFFEFFFF: (1, 47, 62),
                0x00FF00FF00FF00FF: (0, 0, 39),
            },
        ),
    ],
)
def test_the_bitmask_table_holds_each_logical_immediate_once(
    width: Width, count: int, known: dict[int, tuple[int, int, int]]
) -> None:
    """The table built afresh, not the cached one the strategies read: the architecture's
    1302 values at 32 bits and 5334 at 64, none of them zero or all ones, each decoding back
    from its triple, and the canonical (smallest N, immr, imms) triple for hand-worked
    values; all ones and N set at 32 bits are reserved."""
    table = encodings.__wrapped__(width)
    assert len(table) == count
    assert all(0 < value < (1 << width) - 1 for value in table)
    assert all(decode_bitmask(*triple, width) == value for value, triple in table.items())
    assert {value: table[value] for value in known} == known
    assert decode_bitmask(0, 0, 0b111111, width) is None
    assert decode_bitmask(1, 0, 0, Width.W32) is None
