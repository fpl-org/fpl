"""Oracle: printed programs boot on QEMU virt, and what they report is what they compute."""

import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from hypothesis import assume, given
from hypothesis import strategies as st
from riscv_oracle import Boot, assemble, boot, disassemble, dump, link, symbols, toolchain
from riscv_strategies import FRAME_FORMS, blocks, forward_branching, memory_code, straight_line
from riscv_virt import TEST_DEVICE, UART, Block, Regs, Report, Trap, batch, decode, framed

from fpl.asm.riscv.check import check
from fpl.asm.riscv.eval import Halted, Machine, Outcome, run
from fpl.asm.riscv.model import I, OpI, OpR, OpStore, OpUpper, Program, R, Reg, Store, Upper
from fpl.asm.riscv.text import print_program


def uart_byte(char: str) -> Program:
    """Store `char` to the UART, whose address is in x5."""
    return (I(OpI.ADDI, Reg.X6, Reg.X0, ord(char)), Store(OpStore.SB, Reg.X6, Reg.X5, 0))


# 6 * 7 = 42, printed as "42\n" on the UART, then 42 << 16 | 0x3333 to the test device, the
# 42 taken from the product so the exit status observes the multiply.
SMOKE: Program = (
    I(OpI.ADDI, Reg.X10, Reg.X0, 6),
    I(OpI.ADDI, Reg.X11, Reg.X0, 7),
    R(OpR.MUL, Reg.X12, Reg.X10, Reg.X11),
    Upper(OpUpper.LUI, Reg.X5, UART >> 12),
    *uart_byte("4"),
    *uart_byte("2"),
    *uart_byte("\n"),
    Upper(OpUpper.LUI, Reg.X5, TEST_DEVICE >> 12),
    Upper(OpUpper.LUI, Reg.X13, 1 << 4),
    R(OpR.MUL, Reg.X7, Reg.X12, Reg.X13),
    Upper(OpUpper.LUI, Reg.X6, 0x3),
    I(OpI.ADDI, Reg.X6, Reg.X6, 0x333),
    R(OpR.OR, Reg.X7, Reg.X7, Reg.X6),
    Store(OpStore.SW, Reg.X7, Reg.X5, 0),
)


@given(st.just(SMOKE))
def test_a_printed_program_boots_on_virt_prints_42_and_exits_42(program: Program) -> None:
    """[law: virt-smoke] The fixed program, printed and framed, says b"42\\n" and exits 42.

    Its body also comes back from llvm-objdump as the printer's lines, leading tab removed.
    """
    tools = toolchain()
    text = print_program(program)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        assembled = assemble(tools, framed(text), work)
        assert assembled.returncode == 0, assembled.stderr
        linked = link(tools, work)
        assert linked.returncode == 0, linked.stderr
        # _start is the body's first instruction; only the spin follows it.
        assert disassemble(tools, work)[:-1] == [line[1:] for line in text.splitlines()]
        booted = boot(tools, work)
    assert (booted.uart, booted.status) == (b"42\n", 42)


BATCH = 20  # blocks per boot, and instructions per block: a boot costs ~70 ms, a block ~0.3 ms


def booted(batched: Sequence[Block]) -> tuple[dict[str, int], Boot]:
    """Assemble, link and boot `batched` in the batch frame: the symbols' addresses, the boot.

    llvm-mc and ld.lld must both accept the source; a boot past 10 s raises, as a hang.
    """
    tools = toolchain()
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        assembled = assemble(tools, batch(batched), work)
        assert assembled.returncode == 0, assembled.stderr
        linked = link(tools, work)
        assert linked.returncode == 0, linked.stderr
        return symbols(dump(tools, work)), boot(tools, work)


@given(blocks(BATCH, forward_branching(BATCH, FRAME_FORMS)))
def test_checked_forward_branching_batches_halt_on_virt(batched: list[Block]) -> None:
    """[law: checked-programs-halt] A batch the checker accepts boots to exit 0, one report a block.

    Every block is a `forward_branching` program the checker accepts; the batch, in the frame,
    assembles and links, QEMU exits 0 through the test device within 10 s, and the UART holds one
    register report per block and nothing else.
    """
    assume(all(check(block.program) == () for block in batched))
    _, done = booted(batched)
    assert done.status == 0, done
    reports = decode(done.uart)
    assert len(reports) == len(batched), reports
    # A block's report is its registers; a trap in it (cause, address) would stand in their place.
    traps = [(report.cause, hex(report.mepc)) for report in reports if isinstance(report, Trap)]
    assert not traps, traps


def but_x4(values: Sequence[int]) -> tuple[int, ...]:
    """x1..x31 from `values`, x4 (the frame's) left out."""
    return (*values[:3], *values[4:])


@dataclass(frozen=True, slots=True)
class Side:
    """One block of a boot, both ways: QEMU's report, the evaluator's outcome, the block's base."""

    report: Report
    outcome: Outcome
    base: int


def start(block: Block, report: Report) -> Machine:
    """The machine block starts from: its values and window, x3 the window's address.

    The frame sets x3 and blocks never write it, so a register report's x3 slot is that address.
    """
    x3 = report.values[2] if isinstance(report, Regs) else block.regs[2]
    return Machine((0, *block.regs[:2], x3, *block.regs[3:]), block.window)


def both_sides(batched: Sequence[Block]) -> list[Side]:
    """Boot `batched`; it exits 0 with one report per block, set beside the evaluator's run.

    `base` is the address llvm-objdump gives `block<i>`; one step per item is fuel to spare.
    """
    where, done = booted(batched)
    reports = decode(done.uart)
    assert (done.status, len(reports)) == (0, len(batched)), (done, reports)
    sides: list[Side] = []
    for index, (block, report) in enumerate(zip(batched, reports, strict=True)):
        base = where[f"block{index}"]
        outcome = run(block.program, start(block, report), base, len(block.program) + 1)
        sides.append(Side(report, outcome, base))
    return sides


@given(
    blocks(
        BATCH, st.one_of(straight_line(BATCH, FRAME_FORMS), forward_branching(BATCH, FRAME_FORMS))
    )
)
def test_the_evaluator_agrees_with_qemu_block_by_block(batched: list[Block]) -> None:
    """[law: evaluator-agrees-with-qemu] Per block, `run` halts with the registers QEMU reports.

    `base` is the address llvm-objdump gives the block's symbol; the evaluator starts from the
    block's initial values (x3 the frame's), and the 31 registers but x4 it halts with are the
    248 bytes QEMU wrote.
    """
    for index, side in enumerate(both_sides(batched)):
        assert isinstance(side.outcome, Halted), side
        assert isinstance(side.report, Regs), side
        assert but_x4(side.outcome.machine.regs[1:]) == but_x4(side.report.values), batched[index]


@given(blocks(BATCH, memory_code(BATCH)))
def test_the_window_agrees_with_qemu_block_by_block(batched: list[Block]) -> None:
    """[law: window-agrees] Per `memory_code` block, registers and all 256 window bytes agree.

    Loads and stores go through x3 at offsets anywhere in the window, misaligned ones included;
    the evaluator halts with the 31 registers but x4 and the window bytes QEMU dumped.
    """
    for index, side in enumerate(both_sides(batched)):
        assert isinstance(side.outcome, Halted), side
        assert isinstance(side.report, Regs), side
        machine = side.outcome.machine
        assert but_x4(machine.regs[1:]) == but_x4(side.report.values), batched[index]
        assert machine.window == side.report.window, batched[index]
