"""The checker in-process: the strategies split into what it accepts and what it refuses, and
each kind at its boundaries (design section 4)."""

import pytest
from aarch64_strategies import Drawn, far_branches, invalid_programs, programs
from hypothesis import given
from hypothesis import strategies as st

from fpl.asm.aarch64 import model
from fpl.asm.aarch64.check import Kind, Problem, check, reaches
from fpl.asm.aarch64.model import (
    AddSubExtended,
    AddSubImm,
    AddSubShifted,
    Adr,
    Bitfield,
    Branch,
    BranchCond,
    CompareBranch,
    Cond,
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
    Nop,
    Offset,
    OpAddSub,
    OpBitfield,
    OpBranch,
    OpCompareBranch,
    OpCondCompare,
    OpDataProc1,
    OpLoadStore,
    OpLoadStoreUnscaled,
    OpLogical,
    OpLogicalImm,
    OpMoveWide,
    OpPair,
    OpTestBranch,
    Pair,
    PostIndex,
    PreIndex,
    Program,
    Reg,
    RegOffset,
    Shift,
    Width,
)
from fpl.asm.aarch64.text import parse_program, print_program

X1, X2, X3, SP, ZR = Reg.X1, Reg.X2, Reg.X3, Reg.SP, Reg.ZR
W32, W64 = Width.W32, Width.W64
L0 = Label(".L0")
valid = programs().map(lambda p: Drawn(p, None, ()))


@given(st.one_of(valid, invalid_programs(), far_branches()))
def test_check_splits_the_strategies(drawn: Drawn) -> None:
    """[law: strategies-split] The valid strategies draw only programs with check(p) == ();
    every invalid draw has, at each item it replaced, a problem of the kind it drew (on the
    program, index None, for UNDEFINED_LABEL); print then parse is the identity on both."""
    found = check(drawn.program)
    if drawn.kind is None:
        assert found == ()
    at = [None] if drawn.kind is Kind.UNDEFINED_LABEL else drawn.replaced
    for index in at:
        assert any(p.index == index and p.kind is drawn.kind for p in found), (index, found)
    if len(drawn.program) < 1000:  # far k = 20 draws are 262,145 lines; the parser's law is
        assert parse_program(print_program(drawn.program)) == drawn.program  # on the rest


def kinds(*items: Instr | Label) -> list[Kind]:
    """The kinds check finds in a program of `items`."""
    return [problem.kind for problem in check(items)]


@pytest.mark.parametrize(
    ("instr", "found"),
    [
        (AddSubImm(OpAddSub.ADD, W64, X1, X2, 4095, lsl12=False), []),
        (AddSubImm(OpAddSub.ADD, W64, X1, X2, 4096, lsl12=False), [Kind.IMM12]),
        (AddSubImm(OpAddSub.ADD, W64, X1, X2, -1, lsl12=True), [Kind.IMM12]),
        (AddSubImm(OpAddSub.ADD, W64, SP, SP, 0, lsl12=False), []),
        (AddSubImm(OpAddSub.ADDS, W64, SP, X2, 0, lsl12=False), [Kind.REG31]),
        (AddSubImm(OpAddSub.SUBS, W64, ZR, SP, 0, lsl12=False), []),
        (AddSubImm(OpAddSub.ADD, W64, X1, ZR, 1, lsl12=False), [Kind.REG31]),
        (AddSubShifted(OpAddSub.ADD, W32, X1, X2, X3, Shift.ASR, 31), []),
        (AddSubShifted(OpAddSub.ADD, W32, X1, X2, X3, Shift.ASR, 32), [Kind.SHIFT_AMOUNT]),
        (AddSubShifted(OpAddSub.ADD, W64, X1, X2, X3, Shift.ROR, 1), [Kind.SHIFT_AMOUNT]),
        (AddSubShifted(OpAddSub.ADD, W64, SP, X2, X3, Shift.LSL, 0), [Kind.REG31]),
        (AddSubExtended(OpAddSub.ADD, W64, SP, SP, X3, Extend.UXTX, 4), []),
        (AddSubExtended(OpAddSub.ADD, W64, X1, X2, X3, Extend.UXTB, 5), [Kind.EXTEND_AMOUNT]),
        (AddSubExtended(OpAddSub.ADD, W64, X1, X2, X3, Extend.UXTB, -1), [Kind.EXTEND_AMOUNT]),
        (LogicalImm(OpLogicalImm.AND, W64, SP, X2, 0xFF), []),
        (LogicalImm(OpLogicalImm.ANDS, W64, SP, X2, 0xFF), [Kind.REG31]),
        (LogicalImm(OpLogicalImm.AND, W32, X1, X2, 0xFFFFFFFF), [Kind.BITMASK]),
        (LogicalImm(OpLogicalImm.AND, W32, X1, X2, 0x1_0000_00FF), [Kind.BITMASK]),
        (LogicalShifted(OpLogical.ORR, W64, X1, X2, X3, Shift.ROR, 63), []),
        (LogicalShifted(OpLogical.ORR, W64, X1, X2, X3, Shift.ROR, 64), [Kind.SHIFT_AMOUNT]),
        (MoveWide(OpMoveWide.MOVZ, W64, X1, 0xFFFF, 3), []),
        (MoveWide(OpMoveWide.MOVZ, W64, X1, 0x10000, 0), [Kind.MOVE_WIDE]),
        (MoveWide(OpMoveWide.MOVZ, W32, X1, 1, 2), [Kind.MOVE_WIDE]),
        (MoveWide(OpMoveWide.MOVK, W32, X1, -1, 0), [Kind.MOVE_WIDE]),
        (Bitfield(OpBitfield.UBFM, W32, X1, X2, 31, 31), []),
        (Bitfield(OpBitfield.UBFM, W32, X1, X2, 32, 0), [Kind.BITFIELD]),
        (Bitfield(OpBitfield.UBFM, W32, X1, X2, 0, 32), [Kind.BITFIELD]),
        (Extract(W64, X1, X2, X3, 63), []),
        (Extract(W32, X1, X2, X3, 32), [Kind.BITFIELD]),
        (CondCompareReg(OpCondCompare.CCMP, W64, X1, X2, 15, Cond.EQ), []),
        (CondCompareReg(OpCondCompare.CCMP, W64, X1, X2, 16, Cond.EQ), [Kind.COND_IMM]),
        (CondCompareImm(OpCondCompare.CCMN, W64, X1, 31, 15, Cond.EQ), []),
        (CondCompareImm(OpCondCompare.CCMN, W64, X1, 32, 0, Cond.EQ), [Kind.COND_IMM]),
        (CondCompareImm(OpCondCompare.CCMN, W64, X1, 0, 16, Cond.EQ), [Kind.COND_IMM]),
        (DataProc1(OpDataProc1.REV32, W64, X1, X2), []),
        (DataProc1(OpDataProc1.REV32, W32, X1, X2), [Kind.WIDTH]),
        (DataProc1(OpDataProc1.REV, W32, X1, SP), [Kind.REG31]),
    ],
)
def test_operand_ranges_at_their_boundaries(instr: Instr, found: list[Kind]) -> None:
    assert kinds(instr) == found


def load(addr: Offset | PreIndex | PostIndex | RegOffset, rt: Reg = X1) -> LoadStore:
    """`ldr x_, addr`: size 8."""
    return LoadStore(OpLoadStore.LDR_X, rt, addr)


@pytest.mark.parametrize(
    ("instr", "found"),
    [
        (load(Offset(X2, 8 * 4095)), []),
        (load(Offset(X2, 8 * 4096)), [Kind.OFFSET]),
        (load(Offset(X2, 3)), [Kind.OFFSET]),
        (load(Offset(X2, -8)), [Kind.OFFSET]),
        (LoadStore(OpLoadStore.LDRB, X1, Offset(X2, 4095)), []),
        (LoadStore(OpLoadStore.LDRB, X1, Offset(X2, 4096)), [Kind.OFFSET]),
        (load(Offset(ZR, 0)), [Kind.REG31]),
        (load(Offset(SP, 0), rt=SP), [Kind.REG31]),
        (load(PreIndex(X2, -256)), []),
        (load(PreIndex(X2, 256)), [Kind.OFFSET]),
        (load(PostIndex(X2, -257)), [Kind.OFFSET]),
        (load(PostIndex(X1, 8)), [Kind.UNPREDICTABLE]),
        (load(PreIndex(SP, 8), rt=SP), [Kind.REG31]),
        (load(PreIndex(SP, 8), rt=ZR), []),
        (load(RegOffset(X2, X3, Extend.SXTX, s=True)), []),
        (load(RegOffset(X2, X3, Extend.UXTB, s=False)), [Kind.EXTEND_AMOUNT]),
        (load(RegOffset(X2, SP, Extend.UXTX, s=False)), [Kind.REG31]),
        (LoadStoreUnscaled(OpLoadStoreUnscaled.LDUR_X, X1, SP, 255), []),
        (LoadStoreUnscaled(OpLoadStoreUnscaled.LDUR_X, X1, X2, 256), [Kind.OFFSET]),
        (Pair(OpPair.LDP, W64, X1, X2, SP, 504, Mode.OFFSET), []),
        (Pair(OpPair.LDP, W64, X1, X2, X3, 512, Mode.OFFSET), [Kind.OFFSET]),
        (Pair(OpPair.LDP, W64, X1, X2, X3, 4, Mode.PRE), [Kind.OFFSET]),
        (Pair(OpPair.LDPSW, W64, X1, X2, X3, -256, Mode.POST), []),
        (Pair(OpPair.LDPSW, W32, X1, X2, X3, 0, Mode.OFFSET), [Kind.WIDTH]),
        (Pair(OpPair.LDP, W32, X1, X1, X3, 0, Mode.OFFSET), [Kind.UNPREDICTABLE]),
        (Pair(OpPair.STP, W32, X1, X1, X3, 0, Mode.POST), []),
        (Pair(OpPair.STP, W64, X1, X2, X2, 16, Mode.PRE), [Kind.UNPREDICTABLE]),
        (Pair(OpPair.STP, W64, X1, X2, X2, 16, Mode.OFFSET), []),
        (Pair(OpPair.LDPSW, W64, ZR, X2, SP, 16, Mode.POST), []),
    ],
)
def test_addresses_at_their_boundaries(instr: Instr, found: list[Kind]) -> None:
    assert kinds(instr) == found


def reach_of(branch: Instr, distance: int) -> list[Kind]:
    """The kinds found for `branch` to a label `distance` bytes away (nop padding)."""
    nops = (Nop(),) * (abs(distance) // 4)
    if distance > 0:
        return kinds(branch, *nops[1:], L0)
    return kinds(L0, *nops, branch)


@pytest.mark.parametrize(
    ("branch", "k"),
    [
        (model.TestBranch(OpTestBranch.TBZ, X1, 63, L0), 15),
        (CompareBranch(OpCompareBranch.CBZ, W64, X1, L0), 20),
        (BranchCond(Cond.EQ, L0), 20),
        (Adr(X1, L0), 20),
    ],
)
def test_branch_reach_is_exact_both_ways(branch: Instr, k: int) -> None:
    assert reach_of(branch, (1 << k) - 4) == []
    assert reach_of(branch, 1 << k) == [Kind.BRANCH_RANGE]
    assert reach_of(branch, -(1 << k)) == []
    assert reach_of(branch, -(1 << k) - 4) == [Kind.BRANCH_RANGE]


def test_b_reaches_128_mib_each_way() -> None:
    """b and bl at +/-128 MiB are 33 million items, so the reach itself is checked."""
    assert reaches(Branch, (1 << 27) - 4)
    assert not reaches(Branch, 1 << 27)
    assert reaches(Branch, -(1 << 27))
    assert not reaches(Branch, -(1 << 27) - 4)


def test_labels() -> None:
    program: Program = (
        Label(".L0"),
        Branch(OpBranch.B, Label(".Lnowhere")),
        Label(".L0"),
        Label("L1"),
        model.TestBranch(OpTestBranch.TBZ, X1, 64, Label("bad")),
        BranchCond(Cond.NE, Label(".Lnowhere")),
    )
    assert [(p.index, p.kind) for p in check(program)] == [
        (2, Kind.DUPLICATE_LABEL),
        (3, Kind.LABEL_NAME),
        (4, Kind.BITFIELD),
        (4, Kind.LABEL_NAME),
        (None, Kind.UNDEFINED_LABEL),
        (None, Kind.UNDEFINED_LABEL),
    ]
    assert check(program)[-1] == Problem(None, Kind.UNDEFINED_LABEL, "bad")
