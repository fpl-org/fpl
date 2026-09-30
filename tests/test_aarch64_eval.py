"""The reference evaluator in-process (design section 5): data processing and control flow
against goldens worked from the C6.2 pseudocode, flags against an independent computation in
exact integers, division and zero extension pinned, and the evaluator's contracts."""

from collections.abc import Callable, Sequence
from fractions import Fraction

import icontract
import pytest
from aarch64_strategies import forward_branching, register_only
from hypothesis import given
from hypothesis import strategies as st

from fpl.asm.aarch64 import model
from fpl.asm.aarch64.check import slots
from fpl.asm.aarch64.eval import Halted, Machine, Outcome, OutOfFuel, Unmodelled, run
from fpl.asm.aarch64.model import (
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
    Item,
    Label,
    LoadStore,
    LogicalImm,
    LogicalShifted,
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
    OpLogical,
    OpLogicalImm,
    OpMoveWide,
    OpMulAdd,
    OpMulHigh,
    OpMulLong,
    OpTestBranch,
    Reg,
    Shift,
    Width,
)

X0, X1, X2, X3, X4, X30, SP, ZR = Reg.X0, Reg.X1, Reg.X2, Reg.X3, Reg.X4, Reg.X30, Reg.SP, Reg.ZR
W32, W64 = Width.W32, Width.W64
LSL = Shift.LSL
BASE = 0x1_0000
TOP = (1 << 64) - 1
EDGES = [0, 1, 0x7FFF_FFFF, 0x8000_0000, 0xFFFF_FFFF, 1 << 32, (1 << 63) - 1, 1 << 63, TOP]
words = st.one_of(st.sampled_from(EDGES), st.integers(0, TOP))
widths = st.sampled_from(Width)


def machine(nzcv: int = 0, **regs: int) -> Machine:
    """A machine at BASE with x0..x30 zero but for `regs`, named x1=..., and `nzcv`."""
    values = [0] * 31
    for name, value in regs.items():
        values[int(name.removeprefix("x"))] = value
    return Machine(tuple(values), nzcv, BASE)


@st.composite
def machines(draw: st.DrawFn) -> Machine:
    """Any machine: 31 register values, the edges often, four flag bits, an aligned base."""
    regs = tuple(draw(st.lists(words, min_size=31, max_size=31)))
    return Machine(regs, draw(st.integers(0, 15)), 4 * draw(st.integers(0, 1 << 40)))


def halted(program: Sequence[Item], start: Machine, fuel: int = 64) -> Machine:
    """The machine `program` halts in from `start`; fails on any other outcome."""
    outcome = run(tuple(program), start, fuel)
    assert isinstance(outcome, Halted), outcome
    return outcome.machine


def signed(value: int, width: int) -> int:
    """`value`, below 2**width, as two's complement."""
    return value - (1 << width) if value >= 1 << (width - 1) else value


# x0 after one instruction, worked by hand from each page's pseudocode.
ALU: list[tuple[Instr, Machine, int]] = [
    (AddSubImm(OpAddSub.ADD, W64, X0, X1, 5, True), machine(x1=1), 0x5001),
    (AddSubShifted(OpAddSub.SUB, W64, X0, X1, X2, LSL, 4), machine(x1=0x100, x2=1), 0xF0),
    (AddSubShifted(OpAddSub.ADD, W64, X0, X1, X2, Shift.LSR, 4), machine(x1=1, x2=0x100), 0x11),
    (AddSubShifted(OpAddSub.ADD, W32, X0, ZR, X2, Shift.ASR, 4), machine(x2=1 << 31), 0xF800_0000),
    (AddSubShifted(OpAddSub.SUB, W32, X0, ZR, X2, LSL, 0), machine(x2=1), 0xFFFF_FFFF),
    (AddSubExtended(OpAddSub.ADD, W64, X0, X1, X2, Extend.SXTB, 2), machine(x1=1000, x2=0x80), 488),
    (
        AddSubExtended(OpAddSub.SUB, W64, X0, X1, X2, Extend.UXTH, 0),
        machine(x1=1 << 16, x2=0x12345),
        0xDCBB,
    ),
    (AddSubCarry(OpAddSubCarry.ADC, W64, X0, X1, X2), machine(0b0010, x1=5, x2=6), 12),
    (AddSubCarry(OpAddSubCarry.SBC, W64, X0, X1, X2), machine(x1=5, x2=6), TOP - 1),
    (LogicalImm(OpLogicalImm.AND, W64, X0, X1, 0x0F), machine(x1=0xFF), 0x0F),
    (LogicalImm(OpLogicalImm.ORR, W64, X0, X1, 0x0F), machine(x1=0xF0), 0xFF),
    (LogicalImm(OpLogicalImm.EOR, W64, X0, X1, 0x0F), machine(x1=0xFF), 0xF0),
    (LogicalShifted(OpLogical.BIC, W64, X0, X1, X2, LSL, 0), machine(x1=0xFF, x2=0x0F), 0xF0),
    (LogicalShifted(OpLogical.ORN, W32, X0, ZR, X2, LSL, 0), machine(x2=0xFFFF_0000), 0xFFFF),
    (LogicalShifted(OpLogical.EON, W64, X0, X1, ZR, LSL, 0), machine(x1=0xFF), TOP - 0xFF),
    (LogicalShifted(OpLogical.ORR, W64, X0, ZR, X2, Shift.ROR, 4), machine(x2=1), 1 << 60),
    (MoveWide(OpMoveWide.MOVZ, W64, X0, 0x1234, 1), machine(), 0x1234_0000),
    (MoveWide(OpMoveWide.MOVN, W64, X0, 0, 0), machine(), TOP),
    (MoveWide(OpMoveWide.MOVN, W32, X0, 1, 0), machine(), 0xFFFF_FFFE),
    (MoveWide(OpMoveWide.MOVK, W64, X0, 0, 2), machine(x0=TOP), 0xFFFF_0000_FFFF_FFFF),
    (MoveWide(OpMoveWide.MOVK, W32, X0, 0x1234, 0), machine(x0=TOP), 0xFFFF_1234),
    (Bitfield(OpBitfield.UBFM, W64, X0, X1, 4, 7), machine(x1=0xABCD), 0xC),
    (Bitfield(OpBitfield.UBFM, W64, X0, X1, 60, 59), machine(x1=0xABCD), 0xABCD0),
    (Bitfield(OpBitfield.SBFM, W32, X0, X1, 0, 7), machine(x1=0x80), 0xFFFF_FF80),
    (Bitfield(OpBitfield.BFM, W64, X0, X1, 60, 3), machine(x0=0xFFFF, x1=5), 0xFF5F),
    (Extract(W64, X0, X1, X2, 8), machine(x1=0x11, x2=0x2200), 0x1100_0000_0000_0022),
    (DataProc2(OpDataProc2.LSLV, W32, X0, X1, X2), machine(x1=1, x2=33), 2),
    (DataProc2(OpDataProc2.LSRV, W64, X0, X1, X2), machine(x1=0x100, x2=4), 0x10),
    (DataProc2(OpDataProc2.ASRV, W64, X0, X1, X2), machine(x1=1 << 63, x2=63), TOP),
    (DataProc2(OpDataProc2.RORV, W32, X0, X1, X2), machine(x1=1, x2=1), 0x8000_0000),
    (DataProc2(OpDataProc2.UDIV, W64, X0, X1, X2), machine(x1=7, x2=2), 3),
    (DataProc2(OpDataProc2.SDIV, W64, X0, X1, X2), machine(x1=TOP - 6, x2=2), TOP - 2),
    (DataProc1(OpDataProc1.RBIT, W32, X0, X1), machine(x1=1), 0x8000_0000),
    (DataProc1(OpDataProc1.REV16, W32, X0, X1), machine(x1=0x1122_3344), 0x2211_4433),
    (
        DataProc1(OpDataProc1.REV, W64, X0, X1),
        machine(x1=0x0102_0304_0506_0708),
        0x0807_0605_0403_0201,
    ),
    (
        DataProc1(OpDataProc1.REV32, W64, X0, X1),
        machine(x1=0x0102_0304_0506_0708),
        0x0403_0201_0807_0605,
    ),
    (DataProc1(OpDataProc1.CLZ, W64, X0, X1), machine(x1=1), 63),
    (DataProc1(OpDataProc1.CLS, W32, X0, X1), machine(x1=0xFFFF_FF00), 23),
    (DataProc1(OpDataProc1.CLS, W64, X0, X1), machine(), 63),
    (MulAdd(OpMulAdd.MADD, W64, X0, X1, X2, X3), machine(x1=3, x2=4, x3=5), 17),
    (MulAdd(OpMulAdd.MSUB, W32, X0, X1, X2, X3), machine(x1=3, x2=4, x3=5), 0xFFFF_FFF9),
    (MulLong(OpMulLong.SMADDL, X0, X1, X2, X3), machine(x1=0xFFFF_FFFF, x2=2, x3=10), 8),
    (
        MulLong(OpMulLong.UMADDL, X0, X1, X2, X3),
        machine(x1=0xFFFF_FFFF, x2=2, x3=10),
        0x2_0000_0008,
    ),
    (MulLong(OpMulLong.SMSUBL, X0, X1, X2, X3), machine(x1=0xFFFF_FFFF, x2=2, x3=10), 12),
    (
        MulLong(OpMulLong.UMSUBL, X0, X1, X2, X3),
        machine(x1=0xFFFF_FFFF, x2=2, x3=10),
        0xFFFF_FFFE_0000_000C,
    ),
    (MulHigh(OpMulHigh.UMULH, X0, X1, X2), machine(x1=TOP, x2=2), 1),
    (MulHigh(OpMulHigh.SMULH, X0, X1, X2), machine(x1=TOP, x2=2), TOP),
    (CondSelect(OpCondSelect.CSEL, W64, X0, X1, X2, Cond.EQ), machine(0b0100, x1=7, x2=9), 7),
    (CondSelect(OpCondSelect.CSINC, W64, X0, X1, X2, Cond.NE), machine(0b0100, x1=7, x2=9), 10),
    (CondSelect(OpCondSelect.CSINV, W32, X0, X1, X2, Cond.NE), machine(0b0100, x1=7), 0xFFFF_FFFF),
    (CondSelect(OpCondSelect.CSNEG, W64, X0, X1, X2, Cond.NE), machine(0b0100, x2=9), TOP - 8),
    (Nop(), machine(x0=5), 5),
]


@pytest.mark.parametrize(("instr", "start", "x0"), ALU)
def test_data_processing(instr: Instr, start: Machine, x0: int) -> None:
    """Each table row: x0 as the page's pseudocode computes it."""
    assert halted([instr], start).regs[X0] == x0


# NZCV after one instruction: ANDS and BICS set N and Z and clear C and V.
FLAGS: list[tuple[Instr, Machine, int]] = [
    (AddSubShifted(OpAddSub.SUBS, W64, ZR, X1, X2, LSL, 0), machine(x1=5, x2=5), 0b0110),
    (AddSubImm(OpAddSub.ADDS, W32, X0, X1, 1, False), machine(x1=0x7FFF_FFFF), 0b1001),
    (LogicalImm(OpLogicalImm.ANDS, W32, X0, X1, 1 << 31), machine(0b0011, x1=TOP), 0b1000),
    (
        LogicalShifted(OpLogical.BICS, W64, X0, X1, X2, LSL, 0),
        machine(0b0011, x1=0xFF, x2=0xFF),
        0b0100,
    ),
    (
        CondCompareImm(OpCondCompare.CCMP, W64, X1, 5, 0b0010, Cond.NE),
        machine(0b0100, x1=5),
        0b0010,
    ),
    (CondCompareImm(OpCondCompare.CCMN, W64, X1, 1, 0, Cond.EQ), machine(0b0100, x1=TOP), 0b0110),
]


@pytest.mark.parametrize(("instr", "start", "nzcv"), FLAGS)
def test_flags(instr: Instr, start: Machine, nzcv: int) -> None:
    """Each flag-setting form's NZCV, a compare into the zero register included."""
    assert halted([instr], start).nzcv == nzcv


type Flags = dict[str, bool]
# ConditionHolds (J1.4.541) written out per condition, not by its cond<3:1> table.
HOLDS: dict[Cond, Callable[[Flags], bool]] = {
    Cond.EQ: lambda f: f["z"],
    Cond.NE: lambda f: not f["z"],
    Cond.HS: lambda f: f["c"],
    Cond.LO: lambda f: not f["c"],
    Cond.MI: lambda f: f["n"],
    Cond.PL: lambda f: not f["n"],
    Cond.VS: lambda f: f["v"],
    Cond.VC: lambda f: not f["v"],
    Cond.HI: lambda f: f["c"] and not f["z"],
    Cond.LS: lambda f: not f["c"] or f["z"],
    Cond.GE: lambda f: f["n"] == f["v"],
    Cond.LT: lambda f: f["n"] != f["v"],
    Cond.GT: lambda f: not f["z"] and f["n"] == f["v"],
    Cond.LE: lambda f: f["z"] or f["n"] != f["v"],
    Cond.AL: lambda _: True,
    Cond.NV: lambda _: True,
}
SUBTRACTS = (OpAddSub.SUBS, OpAddSubCarry.SBCS, OpCondCompare.CCMP)


@st.composite
def flag_setters(draw: st.DrawFn) -> tuple[Instr, int]:
    """ADDS, SUBS, ADCS, SBCS, CCMN or CCMP of x1 and x2, or of x1 and an immediate (the
    second element; the register forms ignore it)."""
    width, cond, nzcv = draw(widths), draw(st.sampled_from(Cond)), draw(st.integers(0, 15))
    imm = draw(st.integers(0, 31))
    forms: list[Instr] = [AddSubCarry(op, width, X3, X1, X2) for op in OpAddSubCarry]
    forms += [AddSubImm(op, width, X3, X1, imm, False) for op in OpAddSub]
    forms += [AddSubShifted(op, width, X3, X1, X2, LSL, 0) for op in OpAddSub]
    forms += [CondCompareReg(op, width, X1, X2, nzcv, cond) for op in OpCondCompare]
    forms += [CondCompareImm(op, width, X1, imm, nzcv, cond) for op in OpCondCompare]
    return draw(st.sampled_from([i for i in forms if getattr(i, "op", None) in FLAGGED])), imm


FLAGGED = (*OpCondCompare, OpAddSub.ADDS, OpAddSub.SUBS, OpAddSubCarry.ADCS, OpAddSubCarry.SBCS)


def exact_nzcv(x: int, y: int, carry: int, width: int, *, subtract: bool) -> int:
    """NZCV of x + y + carry, or of x - y - (1 - carry), in exact integers: C is the carry
    out of the sum, or no borrow from the difference; V is the signed result out of range."""
    if subtract:
        total, signed_total = x - y - (1 - carry), signed(x, width) - signed(y, width) - (1 - carry)
        c = total >= 0
    else:
        total, signed_total = x + y + carry, signed(x, width) + signed(y, width) + carry
        c = total >= 1 << width
    result = total % (1 << width)
    v = not -(1 << (width - 1)) <= signed_total < 1 << (width - 1)
    return (result >> (width - 1)) << 3 | (result == 0) << 2 | c << 1 | v


@given(flag_setters(), machines())
def test_flags_add_with_carry(drawn: tuple[Instr, int], start: Machine) -> None:
    """[law: flags-add-with-carry] ADDS, SUBS, ADCS, SBCS, CCMN and CCMP (condition true)
    produce the NZCV of AddWithCarry (J1.4.396), checked against an independent 128-bit
    integer computation; a false condition sets NZCV to the immediate."""
    instr, imm = drawn
    width = getattr(instr, "width")  # noqa: B009 -- every drawn form has one; Instr does not
    x, y = start.regs[X1] % (1 << width), start.regs[X2] % (1 << width)
    operand = y if any(slot == "rm" for _, slot, _ in slots(instr)) else imm
    carry_in = start.nzcv >> 1 & 1
    op = getattr(instr, "op")  # noqa: B009 -- as width
    carry = carry_in if isinstance(instr, AddSubCarry) else int(op in SUBTRACTS)
    expected = exact_nzcv(x, operand, carry, width, subtract=op in SUBTRACTS)
    if isinstance(instr, CondCompareReg | CondCompareImm):
        flags = dict(zip("nzcv", (start.nzcv >> at & 1 == 1 for at in (3, 2, 1, 0)), strict=True))
        expected = expected if HOLDS[instr.cond](flags) else instr.nzcv
    assert halted([instr], start).nzcv == expected


def destination(instr: Instr) -> Reg:
    """The instruction's rd."""
    return next(reg for _, slot, reg in slots(instr) if slot == "rd")


def writes_w(instr: Instr) -> bool:
    """A W32 instruction with a destination register."""
    has_rd = any(slot == "rd" for _, slot, _ in slots(instr))
    return has_rd and getattr(instr, "width", None) is W32


@given(st.one_of(*register_only("gp").values()).filter(writes_w), machines())
def test_w_writes_zero_extend(instr: Instr, start: Machine) -> None:
    """[law: w-writes-zero-extend] every instruction of width W32 leaves the destination's
    upper 32 bits zero, including movk, csinv and neg (the goldens pin those three), from
    registers whose upper bits are drawn set."""
    rd = destination(instr)
    assert rd is ZR or halted([instr], start).regs[rd] < 1 << 32


DIVISORS = st.one_of(st.sampled_from([0, 1, 1 << 32, 0xFFFF_FFFF, TOP]), words)


@given(st.sampled_from([OpDataProc2.SDIV, OpDataProc2.UDIV]), widths, words, DIVISORS)
def test_division_by_zero_is_zero(op: OpDataProc2, width: Width, x: int, y: int) -> None:
    """[law: division-by-zero-is-zero] sdiv and udiv by zero give 0 in both widths,
    INT_MIN / -1 gives INT_MIN, and elsewhere the quotient rounds toward zero (a Fraction
    truncated, read at the width from full 64-bit registers)."""
    a, b = x % (1 << width), y % (1 << width)
    if op is OpDataProc2.SDIV:
        a, b = signed(a, width), signed(b, width)
    quotient = int(Fraction(a, b)) if b else 0
    got = halted([DataProc2(op, width, X0, X1, X2)], machine(x1=x, x2=y)).regs[X0]
    assert got == quotient % (1 << width)


@pytest.mark.parametrize("width", Width)
def test_division_pins(width: Width) -> None:
    """INT_MIN / -1 is INT_MIN, and division by zero is 0, both signed and unsigned."""
    int_min, minus_one = 1 << (width - 1), (1 << width) - 1
    sdiv = DataProc2(OpDataProc2.SDIV, width, X0, X1, X2)
    udiv = DataProc2(OpDataProc2.UDIV, width, X3, X1, ZR)
    after = halted([sdiv, udiv], machine(x0=7, x1=int_min, x2=minus_one, x3=7))
    assert (after.regs[X0], after.regs[X3]) == (int_min, 0)
    assert halted([sdiv], machine(x0=7, x1=int_min)).regs[X0] == 0


L1, END = Label(".L1"), Label(".Lend")
MOV = MoveWide(OpMoveWide.MOVZ, W64, X0, 1, 0)
CONTROL: list[tuple[list[Item], Machine, Outcome]] = [
    ([Branch(OpBranch.B, L1), MOV, L1], machine(), Halted(machine())),
    ([Branch(OpBranch.BL, L1), Nop(), L1], machine(), Halted(machine(x30=BASE + 4))),
    ([BranchCond(Cond.EQ, L1), MOV, L1], machine(0b0100), Halted(machine(0b0100))),
    ([BranchCond(Cond.EQ, L1), MOV, L1], machine(), Halted(machine(x0=1))),
    (
        [CompareBranch(OpCompareBranch.CBZ, W32, X1, L1), MOV, L1],
        machine(x1=1 << 32),
        Halted(machine(x1=1 << 32)),
    ),
    ([CompareBranch(OpCompareBranch.CBNZ, W64, X1, L1), MOV, L1], machine(), Halted(machine(x0=1))),
    (
        [model.TestBranch(OpTestBranch.TBZ, X1, 40, L1), MOV, L1],
        machine(x1=1 << 40),
        Halted(machine(x0=1, x1=1 << 40)),
    ),
    (
        [model.TestBranch(OpTestBranch.TBNZ, X1, 40, L1), MOV, L1],
        machine(x1=1 << 40),
        Halted(machine(x1=1 << 40)),
    ),
    (
        [Adr(X4, END), BranchReg(OpBranchReg.BR, X4), MOV, END],
        machine(),
        Halted(machine(x4=BASE + 12)),
    ),
    (
        [Adr(X4, L1), BranchReg(OpBranchReg.BLR, X4), Nop(), L1, Nop()],
        machine(),
        Halted(machine(x4=BASE + 12, x30=BASE + 8)),
    ),
    (
        [BranchReg(OpBranchReg.RET, X30), MOV, Nop()],
        machine(x30=BASE + 8),
        Halted(machine(x30=BASE + 8)),
    ),
    ([L1, Branch(OpBranch.B, L1)], machine(), OutOfFuel()),
]


@pytest.mark.parametrize(("program", "start", "outcome"), CONTROL)
def test_control(program: list[Item], start: Machine, outcome: Outcome) -> None:
    """Branches, links and register targets within the program; a loop runs out of fuel."""
    assert run(tuple(program), start, 16) == outcome


@pytest.mark.parametrize(
    ("program", "start", "index", "why"),
    [
        ([BranchReg(OpBranchReg.BR, X1)], machine(x1=BASE + 2), 0, "not base + 4i"),
        ([BranchReg(OpBranchReg.BR, X1)], machine(x1=BASE + 8), 0, "not base + 4i"),
        ([BranchReg(OpBranchReg.BR, X1)], machine(x1=BASE - 4), 0, "not base + 4i"),
        ([Nop(), L1, AddSubImm(OpAddSub.ADD, W64, X1, SP, 0, False)], machine(), 1, "sp"),
        ([LoadStore(OpLoadStore.LDR_X, X1, Offset(X2, 0))], machine(), 0, "memory"),
    ],
)
def test_unmodelled(program: list[Item], start: Machine, index: int, why: str) -> None:
    """A register target off the program's instructions, an sp form and a memory access
    are Unmodelled at their instruction index, saying why."""
    outcome = run(tuple(program), start, 16)
    assert isinstance(outcome, Unmodelled)
    assert outcome.index == index
    assert why in outcome.why


def test_fuel() -> None:
    """Fuel counts instructions: one suffices for one, none halts only the empty program."""
    assert run((Nop(),), machine(), 1) == Halted(machine())
    assert run((Nop(),), machine(), 0) == OutOfFuel()
    assert run((), machine(), 0) == Halted(machine())


@given(forward_branching(), machines(), st.integers(0, 40))
def test_evaluator_contracts(program: tuple[Item, ...], start: Machine, fuel: int) -> None:
    """[law: evaluator-contracts] the four contracts of section 5 hold on every call, icontract
    checking each (CrossHair checks them in make harden): every register stays in
    [0, 2**64), W results below 2**32, nzcv in [0, 16), and run keeps base."""
    outcome = run(program, start, fuel)
    assert isinstance(outcome, Halted | OutOfFuel)
    if isinstance(outcome, Halted):
        after = outcome.machine
        assert after.base == start.base
        assert 0 <= after.nzcv < 16
        assert all(0 <= value < 1 << 64 for value in after.regs)


def test_contracts_are_on() -> None:
    """run refuses a machine without 31 registers: the precondition is checked."""
    with pytest.raises(icontract.ViolationError):
        run((), Machine((0,), 0, BASE), 1)
