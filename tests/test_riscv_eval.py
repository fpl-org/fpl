"""The reference evaluator in process: each table row by a hand-derived golden, the run loop."""

import pytest
from hypothesis import given
from hypothesis import strategies as st
from riscv_strategies import STRAIGHT, between, instructions

from fpl.asm.riscv.eval import Halted, Machine, OutOfFuel, Trapped, Unmodelled, run
from fpl.asm.riscv.model import (
    Access,
    Bare,
    Fence,
    I,
    Instr,
    Jalr,
    Load,
    OpBare,
    OpI,
    OpLoad,
    OpR,
    OpShift,
    OpStore,
    OpUpper,
    Program,
    R,
    Reg,
    Shift,
    Store,
    Upper,
)

BASE = 0x8000_0000
ONES = (1 << 64) - 1
MINUS_7 = 0xFFFF_FFFF_FFFF_FFF9
NOP = I(OpI.ADDI, Reg.X0, Reg.X0, 0)


def machine(values: dict[Reg, int]) -> Machine:
    """Every register 0 except the ones `values` names."""
    return Machine(tuple(values.get(reg, 0) for reg in Reg))


def halted(program: Program, start: Machine) -> Machine:
    """The machine `program` halts with from `start`, at `BASE`, with fuel to spare."""
    outcome = run(program, start, BASE, 1000)
    assert isinstance(outcome, Halted)
    return outcome.machine


def x3(instr: Instr, a: int = MINUS_7, b: int = 2) -> int:
    """x3 after `instr` alone, from x1 = `a` and x2 = `b`."""
    return halted((instr,), machine({Reg.X1: a, Reg.X2: b})).regs[Reg.X3]


def r(op: OpR) -> R:
    return R(op, Reg.X3, Reg.X1, Reg.X2)


# Each row from x1 = -7 and x2 = 2, derived by hand from 2.4, 4.2 and chapter 12.
GOLDEN: tuple[tuple[Instr, int], ...] = (
    (r(OpR.ADD), 0xFFFF_FFFF_FFFF_FFFB),
    (r(OpR.SUB), 0xFFFF_FFFF_FFFF_FFF7),
    (r(OpR.SLL), 0xFFFF_FFFF_FFFF_FFE4),
    (r(OpR.SLT), 1),
    (r(OpR.SLTU), 0),
    (r(OpR.XOR), 0xFFFF_FFFF_FFFF_FFFB),
    (r(OpR.SRL), 0x3FFF_FFFF_FFFF_FFFE),
    (r(OpR.SRA), 0xFFFF_FFFF_FFFF_FFFE),
    (r(OpR.OR), 0xFFFF_FFFF_FFFF_FFFB),
    (r(OpR.AND), 0),
    (r(OpR.ADDW), 0xFFFF_FFFF_FFFF_FFFB),
    (r(OpR.SUBW), 0xFFFF_FFFF_FFFF_FFF7),
    (r(OpR.SLLW), 0xFFFF_FFFF_FFFF_FFE4),
    (r(OpR.SRLW), 0x3FFF_FFFE),
    (r(OpR.SRAW), 0xFFFF_FFFF_FFFF_FFFE),
    (r(OpR.MUL), 0xFFFF_FFFF_FFFF_FFF2),
    (r(OpR.MULH), ONES),
    (r(OpR.MULHSU), ONES),
    (r(OpR.MULHU), 1),
    (r(OpR.DIV), 0xFFFF_FFFF_FFFF_FFFD),
    (r(OpR.DIVU), 0x7FFF_FFFF_FFFF_FFFC),
    (r(OpR.REM), ONES),
    (r(OpR.REMU), 1),
    (r(OpR.MULW), 0xFFFF_FFFF_FFFF_FFF2),
    (r(OpR.DIVW), 0xFFFF_FFFF_FFFF_FFFD),
    (r(OpR.DIVUW), 0x7FFF_FFFC),
    (r(OpR.REMW), ONES),
    (r(OpR.REMUW), 1),
    (I(OpI.ADDI, Reg.X3, Reg.X1, 3), 0xFFFF_FFFF_FFFF_FFFC),
    (I(OpI.SLTI, Reg.X3, Reg.X1, 3), 1),
    (I(OpI.SLTIU, Reg.X3, Reg.X1, -1), 1),
    (I(OpI.XORI, Reg.X3, Reg.X1, 3), 0xFFFF_FFFF_FFFF_FFFA),
    (I(OpI.ORI, Reg.X3, Reg.X1, 3), 0xFFFF_FFFF_FFFF_FFFB),
    (I(OpI.ANDI, Reg.X3, Reg.X1, 3), 1),
    (I(OpI.ADDIW, Reg.X3, Reg.X1, 3), 0xFFFF_FFFF_FFFF_FFFC),
    (Shift(OpShift.SLLI, Reg.X3, Reg.X1, 4), 0xFFFF_FFFF_FFFF_FF90),
    (Shift(OpShift.SRLI, Reg.X3, Reg.X1, 60), 0xF),
    (Shift(OpShift.SRAI, Reg.X3, Reg.X1, 60), ONES),
    (Shift(OpShift.SLLIW, Reg.X3, Reg.X1, 28), 0xFFFF_FFFF_9000_0000),
    (Shift(OpShift.SRLIW, Reg.X3, Reg.X1, 28), 0xF),
    (Shift(OpShift.SRAIW, Reg.X3, Reg.X1, 28), ONES),
    (Upper(OpUpper.LUI, Reg.X3, 0x80001), 0xFFFF_FFFF_8000_1000),
    (Upper(OpUpper.AUIPC, Reg.X3, 1), BASE + 0x1000),
    (Upper(OpUpper.AUIPC, Reg.X3, 0x80000), 0),
)


def test_the_goldens_cover_every_arithmetic_op() -> None:
    assert {instr.op for instr, _ in GOLDEN} == {*OpR, *OpI, *OpShift, *OpUpper}


@pytest.mark.parametrize(("instr", "expected"), GOLDEN)
def test_each_table_row_gives_its_golden(instr: Instr, expected: int) -> None:
    assert x3(instr) == expected


def test_a_write_to_x0_is_discarded() -> None:
    assert halted((R(OpR.ADD, Reg.X0, Reg.X1, Reg.X1),), machine({Reg.X1: 1})).regs[0] == 0


@pytest.mark.parametrize(("op", "cause"), [(OpBare.ECALL, 11), (OpBare.EBREAK, 3)])
def test_ecall_and_ebreak_trap_with_their_machine_cause(op: OpBare, cause: int) -> None:
    """The QEMU virt EEI in M-mode: the probe exits 11 for ecall and 3 for ebreak."""
    start = machine({Reg.X1: 5})
    outcome = run((NOP, Bare(op), NOP), start, BASE, 10)
    assert isinstance(outcome, Trapped)
    assert (outcome.cause, outcome.index, outcome.machine) == (cause, 1, start)


def test_fences_do_nothing_on_one_hart() -> None:
    start = machine({Reg.X1: 5})
    program = (Fence(Access.R, Access.W), Bare(OpBare.FENCE_TSO))
    assert halted(program, start) == start


UNMODELLED = (
    Load(OpLoad.LD, Reg.X1, Reg.X2, 0),
    Store(OpStore.SD, Reg.X1, Reg.X2, 0),
    Jalr(Reg.X1, Reg.X2, 0),
)


@pytest.mark.parametrize("instr", UNMODELLED)
def test_an_unmodelled_instruction_ends_the_run_naming_itself(instr: Instr) -> None:
    outcome = run((NOP, instr), machine({}), BASE, 10)
    assert isinstance(outcome, Unmodelled)
    assert (outcome.index, instr.op in outcome.why) == (1, True)


def test_fuel_bounds_the_steps() -> None:
    assert run((NOP, NOP), machine({}), BASE, 1) == OutOfFuel()
    assert run((NOP, NOP), machine({}), BASE, 2) == Halted(machine({}))


registers = st.lists(between(0, (1 << 64) - 1), min_size=31, max_size=31).map(
    lambda values: Machine((0, *values))
)


@given(st.lists(instructions(*STRAIGHT), max_size=20), registers)
def test_straight_line_code_halts_in_range_with_x0_zero(body: list[Instr], start: Machine) -> None:
    """One step per instruction; every register stays in [0, 2**64) and x0 stays 0."""
    outcome = run(tuple(body), start, BASE, len(body))
    assert isinstance(outcome, Halted)
    assert outcome.machine.regs[0] == 0
    assert all(0 <= value < 1 << 64 for value in outcome.machine.regs)
