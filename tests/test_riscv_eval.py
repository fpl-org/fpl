"""The reference evaluator in process: each table row by a hand-derived golden, the run loop."""

import math
from fractions import Fraction
from itertools import product

import icontract
import pytest
from hypothesis import given
from hypothesis import strategies as st
from riscv_strategies import STRAIGHT, between, forward_branching, instructions

from fpl.asm.riscv.eval import (
    Halted,
    Machine,
    OutOfFuel,
    Trapped,
    Unmodelled,
    alu,
    run,
    sext,
)
from fpl.asm.riscv.model import (
    Access,
    Bare,
    Branch,
    Fence,
    I,
    Instr,
    Jal,
    Jalr,
    Label,
    Load,
    OpBare,
    OpBranch,
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
    start = Machine(machine({Reg.X1: 5}).regs, bytes(range(8)))
    outcome = run((NOP, Bare(op), NOP), start, BASE, 10)
    assert isinstance(outcome, Trapped)
    assert (outcome.cause, outcome.index, outcome.machine) == (cause, 1, start)


def test_fences_do_nothing_on_one_hart() -> None:
    start = machine({Reg.X1: 5})
    program = (Fence(Access.R, Access.W), Bare(OpBare.FENCE_TSO))
    assert halted(program, start) == start


WINDOW = 0x8000_1000  # where x3 points: the window's first byte
SIZES = {
    "b": 1,
    "h": 2,
    "w": 4,
    "d": 8,
}  # a load's or store's second letter names its size


def size(op: OpLoad | OpStore) -> int:
    """The bytes `op` accesses, read off its mnemonic."""
    return SIZES[op[1]]


def windowed(window: bytes, values: dict[Reg, int]) -> Machine:
    """The registers `values` names, x3 pointing at `window`, which the machine holds."""
    return Machine(machine({Reg.X3: WINDOW, **values}).regs, window)


@given(
    st.sampled_from(OpStore),
    st.sampled_from(OpLoad),
    st.binary(min_size=256, max_size=256),
    between(0, ONES),
    st.data(),
)
def test_stores_and_loads_in_the_window_are_little_endian_at_any_offset(
    store: OpStore, load: OpLoad, window: bytes, value: int, data: st.DataObject
) -> None:
    """A store writes the low bytes of rs2 at any offset in the window, aligned or not; a load
    reads its bytes back, sign-extended unless its mnemonic ends in `u`."""
    at = data.draw(between(0, 256 - size(store)))
    back = data.draw(between(0, 256 - size(load)))
    program = (Store(store, Reg.X1, Reg.X3, at), Load(load, Reg.X2, Reg.X3, back))
    after = halted(program, windowed(window, {Reg.X1: value}))
    expected = bytearray(window)
    expected[at : at + size(store)] = value.to_bytes(8, "little")[: size(store)]
    loaded = int.from_bytes(expected[back : back + size(load)], "little")
    bits = 8 * size(load)
    if not load.endswith("u") and loaded >> (bits - 1):
        loaded += ONES + 1 - (1 << bits)
    assert after.window == bytes(expected)
    assert after.regs == windowed(window, {Reg.X1: value, Reg.X2: loaded}).regs


OUTSIDE = (
    Load(OpLoad.LB, Reg.X1, Reg.X3, -1),
    Load(OpLoad.LBU, Reg.X1, Reg.X3, 256),
    Load(OpLoad.LH, Reg.X1, Reg.X3, 255),
    Load(OpLoad.LD, Reg.X1, Reg.X3, 249),
    Store(OpStore.SB, Reg.X1, Reg.X3, -1),
    Store(OpStore.SW, Reg.X1, Reg.X3, 253),
    Load(OpLoad.LD, Reg.X1, Reg.X2, 0),
)


@pytest.mark.parametrize("instr", OUTSIDE)
def test_an_access_leaving_the_window_is_unmodelled_naming_itself(
    instr: Load | Store,
) -> None:
    """A byte outside the 256 at x3 is real RAM or a fault: the evaluator does not know which."""
    outcome = run((NOP, instr), windowed(bytes(256), {}), BASE, 10)
    assert isinstance(outcome, Unmodelled)
    assert (outcome.index, instr.op in outcome.why) == (1, True)


def test_without_a_window_every_access_is_unmodelled() -> None:
    outcome = run((Load(OpLoad.LB, Reg.X1, Reg.X3, 0),), windowed(b"", {}), BASE, 10)
    assert isinstance(outcome, Unmodelled)


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


def addi(rd: Reg, rs1: Reg, imm: int) -> I:
    return I(OpI.ADDI, rd, rs1, imm)


LOOP = Label(".Lloop")
# x2 += 3, five times: 15 steps, the branch back taken four times.
COUNTDOWN: Program = (
    LOOP,
    addi(Reg.X2, Reg.X2, 3),
    addi(Reg.X1, Reg.X1, -1),
    Branch(OpBranch.BNE, Reg.X1, Reg.X0, LOOP),
)


def test_a_loop_runs_until_its_branch_falls_through() -> None:
    assert run(COUNTDOWN, machine({Reg.X1: 5}), BASE, 15) == Halted(machine({Reg.X2: 15}))
    assert run(COUNTDOWN, machine({Reg.X1: 5}), BASE, 14) == OutOfFuel()


SKIP = Label(".Lskip")


@pytest.mark.parametrize(
    ("op", "taken"),
    [
        (OpBranch.BEQ, False),
        (OpBranch.BNE, True),
        (OpBranch.BLT, True),
        (OpBranch.BGE, False),
        (OpBranch.BLTU, False),
        (OpBranch.BGEU, True),
    ],
)
def test_each_branch_compares_as_its_mnemonic_says(op: OpBranch, taken: bool) -> None:
    """x1 = -1 and x2 = 1: less signed, greater unsigned, unequal."""
    program = (Branch(op, Reg.X1, Reg.X2, SKIP), addi(Reg.X3, Reg.X0, 1), SKIP)
    assert halted(program, machine({Reg.X1: ONES, Reg.X2: 1})).regs[Reg.X3] == (not taken)


END = Label(".Lend")


def test_jal_links_the_next_address_and_jumps_to_its_label() -> None:
    program = (NOP, Jal(Reg.X1, END), addi(Reg.X3, Reg.X0, 1), END)
    assert halted(program, machine({})) == machine({Reg.X1: BASE + 8})


def test_jalr_clears_bit_0_and_links_after_reading_rs1() -> None:
    """rd is rs1: the target comes from the old x5, the link replaces it."""
    program = (
        Jalr(Reg.X5, Reg.X5, 1),
        addi(Reg.X3, Reg.X0, 1),
        addi(Reg.X4, Reg.X0, 3),
    )
    after = halted(program, machine({Reg.X5: BASE + 8}))
    assert after == machine({Reg.X4: 3, Reg.X5: BASE + 4})


@pytest.mark.parametrize("target", [BASE - 4, BASE + 2, BASE + 8, ONES])
def test_jalr_to_no_instruction_of_the_program_is_unmodelled(target: int) -> None:
    outcome = run((NOP, Jalr(Reg.X1, Reg.X5, 0)), machine({Reg.X5: target}), BASE, 10)
    assert isinstance(outcome, Unmodelled)
    assert (outcome.index, f"{target & ~1:#x}" in outcome.why) == (1, True)


@pytest.mark.parametrize("jump", [Jal(Reg.X1, END), Branch(OpBranch.BEQ, Reg.X0, Reg.X0, END)])
def test_a_jump_to_an_undefined_label_is_unmodelled(jump: Jal | Branch) -> None:
    outcome = run((NOP, jump), machine({}), BASE, 10)
    assert outcome == Unmodelled(1, ".Lend is not defined")


DIVISIONS = (
    OpR.DIV,
    OpR.DIVU,
    OpR.REM,
    OpR.REMU,
    OpR.DIVW,
    OpR.DIVUW,
    OpR.REMW,
    OpR.REMUW,
)
EDGES = (
    0,
    1,
    ONES,
    1 << 63,
    (1 << 63) - 1,
    1 << 31,
    (1 << 32) - 1,
    0xFFFF_FFFF_8000_0000,
)
operands = st.one_of(st.sampled_from(EDGES), between(0, ONES))


def as_int(value: int, width: int, *, signed: bool) -> int:
    """The low `width` bits of `value`, read signed or unsigned."""
    low = value % (1 << width)
    return low - (1 << width) if signed and low >> (width - 1) else low


def register(value: int, width: int) -> int:
    """A `width`-bit result as the register holds it: sign-extended to 64 bits."""
    return as_int(value, width, signed=True) % (1 << 64)


@given(st.sampled_from(DIVISIONS), operands, operands)
def test_division_follows_table_11(op: OpR, a: int, b: int) -> None:
    """[law: division-table-11] At divisor zero the quotient is all ones and the remainder the
    dividend; at signed overflow the quotient is the dividend and the remainder 0; elsewhere the
    quotient is the exact one truncated toward zero, and the remainder what it leaves. The W
    forms read the low 32 bits and sign-extend the 32-bit result."""
    width = 32 if op.endswith("w") else 64
    signed = not op.removesuffix("w").endswith("u")
    x, y = as_int(a, width, signed=signed), as_int(b, width, signed=signed)
    if y == 0:
        quotient, rest = -1, x
    elif signed and (x, y) == (-(1 << (width - 1)), -1):
        quotient, rest = x, 0
    else:
        quotient = math.trunc(Fraction(x, y))
        rest = x - y * quotient
    expected = quotient if op.startswith("div") else rest
    assert x3(r(op), a, b) == register(expected, width)


@pytest.mark.parametrize(
    ("op", "a", "b", "expected"),
    [
        (OpR.DIV, 5, 0, ONES),
        (OpR.DIVU, 5, 0, ONES),
        (OpR.REM, 5, 0, 5),
        (OpR.REMU, ONES, 0, ONES),
        (OpR.DIV, 1 << 63, ONES, 1 << 63),
        (OpR.REM, 1 << 63, ONES, 0),
        (OpR.DIVW, 5, 0, ONES),
        (OpR.DIVUW, 5, 0, ONES),
        (OpR.REMW, 5, 0, 5),
        (OpR.REMUW, 0x8000_0005, 0, 0xFFFF_FFFF_8000_0005),
        (OpR.DIVW, 0x8000_0000, ONES, 0xFFFF_FFFF_8000_0000),
        (OpR.REMW, 0x8000_0000, ONES, 0),
    ],
)
def test_table_11_row_by_row(op: OpR, a: int, b: int, expected: int) -> None:
    assert x3(r(op), a, b) == expected


W_SHIFTS = (OpR.SLLW, OpR.SRLW, OpR.SRAW)


@st.composite
def w_forms(draw: st.DrawFn) -> tuple[Instr, ...]:
    """Every W form, lui and auipc once each, from x1 (and x2) to x3, their immediates drawn."""
    amount, imm, upper = (
        draw(between(0, 31)),
        draw(between(-2048, 2047)),
        draw(between(0, (1 << 20) - 1)),
    )
    return (
        *(R(op, Reg.X3, Reg.X1, Reg.X2) for op in OpR if op.endswith("w")),
        *(
            Shift(op, Reg.X3, Reg.X1, amount)
            for op in (OpShift.SLLIW, OpShift.SRLIW, OpShift.SRAIW)
        ),
        I(OpI.ADDIW, Reg.X3, Reg.X1, imm),
        *(Upper(op, Reg.X3, upper) for op in OpUpper),
    )


def is_word(value: int) -> bool:
    """Bits 63 to 31 are equal: `value` is its low 32 bits sign-extended."""
    return value >> 31 in (0, (1 << 33) - 1)


def assert_word(instr: Instr, a: int, b: int, high: int) -> None:
    """`instr`'s result from x1 = a, x2 = b is a sign-extended word, as w-ops-sign-extend says."""
    result = x3(instr, a, b)
    if isinstance(instr, Upper):
        result = (result - BASE) % (1 << 64) if instr.op is OpUpper.AUIPC else result
        assert result % (1 << 32) == (instr.imm << 12) % (1 << 32)
    assert is_word(result), instr
    if isinstance(instr, R) and instr.op in W_SHIFTS:
        assert x3(instr, a, b ^ 32) == result, instr
        assert x3(instr, a, b ^ (high << 5)) == result, instr


@given(w_forms(), operands, operands, st.integers(1, (1 << 59) - 1))
def test_w_forms_sign_extend_32_bits(forms: tuple[Instr, ...], a: int, b: int, high: int) -> None:
    """[law: w-ops-sign-extend] Every W form's result is its low 32 bits sign-extended; so is
    lui's, and auipc's offset from its own address, whose low 32 bits are the immediate's; the
    register W shifts read only the low 5 bits of the amount (bit 5 flipped, and any above it).
    Every form sees every drawn pair."""
    for instr in forms:
        assert_word(instr, a, b, high)


# Operand pairs every ALU row is also given: the extremes of both widths, both ways round.
ALU_EDGES = tuple(product((0, 1, ONES, 1 << 63, (1 << 63) - 1, 0xFFFF_FFFF_8000_0000), repeat=2))


@given(forward_branching(20), registers, operands, operands)
def test_the_evaluator_keeps_its_contracts(
    program: Program, start: Machine, a: int, b: int
) -> None:
    """[law: evaluator-contracts] A forward-branching program halts within one step per
    instruction, every register in range and x0 zero; every ALU row, on the drawn pair and on
    each edge pair, and `sext` at every width of the operands' difference, give values in
    `[0, 2**64)`. icontract checks on every call."""
    outcome = run(program, start, BASE, sum(not isinstance(item, Label) for item in program))
    assert isinstance(outcome, Halted)
    assert outcome.machine.regs[0] == 0
    assert all(0 <= reg <= ONES for reg in outcome.machine.regs)
    for op, (x, y) in product(OpR, ((a, b), *ALU_EDGES)):
        assert 0 <= alu(op, x, y) <= ONES, (op, x, y)
    assert all(0 <= sext(a - b, bits) <= ONES for bits in (8, 12, 16, 32, 64))


@pytest.mark.parametrize("regs", [(1,) + (0,) * 31, (0,) * 31, (0, -1) + (0,) * 30])
def test_run_refuses_a_machine_that_is_not_well_formed(regs: tuple[int, ...]) -> None:
    with pytest.raises(icontract.ViolationError):
        run((NOP,), Machine(regs), BASE, 1)


def test_sext_takes_every_width_from_one_bit_and_refuses_zero() -> None:
    assert (sext(1, 1), sext(2, 1)) == (ONES, 0)
    with pytest.raises(icontract.ViolationError):
        sext(1, 0)


@pytest.mark.parametrize(("a", "b"), [(1 << 64, 0), (0, -1)])
def test_alu_refuses_an_operand_that_is_not_a_register_value(a: int, b: int) -> None:
    with pytest.raises(icontract.ViolationError):
        alu(OpR.AND, a, b)


def test_jalr_may_go_to_the_first_instruction() -> None:
    assert isinstance(run((Jalr(Reg.X0, Reg.X5, 0),), machine({Reg.X5: BASE}), BASE, 3), OutOfFuel)
