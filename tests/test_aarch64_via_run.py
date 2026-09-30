"""Oracle tests on the machine itself: natively on Darwin, under qemu-aarch64 on Linux."""

import os

import pytest
from aarch64_frame import OBSERVED, RECORD, Block, frame, records
from aarch64_oracle import assemble, execute, link, toolchain
from aarch64_strategies import blocks
from hypothesis import given, settings
from hypothesis import strategies as st

from fpl.asm.aarch64.check import check
from fpl.asm.aarch64.eval import Halted, Machine, run
from fpl.asm.aarch64.model import MoveWide, MulAdd, OpMoveWide, OpMulAdd, Reg, Width
from fpl.asm.aarch64.text import print_program

SMOKE = (
    MoveWide(OpMoveWide.MOVZ, Width.W64, Reg.X0, 6, 0),
    MoveWide(OpMoveWide.MOVZ, Width.W64, Reg.X1, 7, 0),
    MulAdd(OpMulAdd.MADD, Width.W64, Reg.X0, Reg.X0, Reg.X1, Reg.ZR),
)


@given(st.just(SMOKE))
def test_native_smoke(
    tmp_path_factory: pytest.TempPathFactory, worker_id: str, block: tuple[MoveWide | MulAdd, ...]
) -> None:
    """[law: native-smoke] The smoke block, built from IR values and printed by the printer,
    runs in the platform's frame to exit 0 and one 256-byte record: x0 42, x1 7, index 0."""
    tools = toolchain(tmp_path_factory, worker_id)
    text = print_program(block)
    assert text == "\tmov\tx0, #6\n\tmov\tx1, #7\n\tmul\tx0, x0, x1\n"
    work = tmp_path_factory.mktemp("smoke")
    built = assemble(tools, frame(tools.system, [Block((0,) * 31, 0, block)]), work)
    assert built.returncode == 0, built.stderr.decode()
    linked = link(tools, work)
    assert linked.returncode == 0, linked.stderr.decode()
    done = execute(tools, work)
    assert done.returncode == 0
    assert len(done.stdout) == RECORD
    (record,) = records(done, 1)
    assert (record.regs[0], record.regs[1], record.index) == (42, 7, 0)
    assert record.nzcv == 0  # the frame sets NZCV to 0 and neither mov nor mul sets it


# Each example links and runs a fresh executable, 0.3 s on a Mac (hole first-exec-cost), so the
# run laws draw fewer examples than the profile's count and share one batch (oracle-settings).
PROFILE = os.environ.get("HYPOTHESIS_PROFILE", "quick")
RUN = settings(
    backend="hypothesis",
    deadline=None,
    max_examples={"quick": 4, "harden": 20, "symbolic": 4}[PROFILE],
)


@RUN
@given(batch=blocks())
def test_checked_blocks_run_as_the_evaluator_runs_them(
    tmp_path_factory: pytest.TempPathFactory, worker_id: str, batch: list[Block]
) -> None:
    """[law: checked-programs-run] [law: evaluator-agrees-with-run] One batch of checked
    straight_line and forward_branching blocks assembles and links with exit 0 and runs to
    exit 0 within 10 s with one record per block, in order; and for each block, with base
    from its record, `run` returns Halted(m) with m.regs at the 29 observed registers and
    m.nzcv equal to the record. One run serves both laws (design section 7)."""
    tools = toolchain(tmp_path_factory, worker_id)
    assert [check(block.program) for block in batch] == [()] * len(batch)
    work = tmp_path_factory.mktemp("run")
    built = assemble(tools, frame(tools.system, batch), work)
    assert built.returncode == 0, built.stderr.decode()
    linked = link(tools, work)
    assert linked.returncode == 0, linked.stderr.decode()
    found = records(execute(tools, work), len(batch))
    for block, record in zip(batch, found, strict=True):
        start = Machine(block.regs, block.nzcv, record.base)
        outcome = run(block.program, start, len(block.program) + 1)
        assert isinstance(outcome, Halted), (record.index, outcome)
        observed = {reg: outcome.machine.regs[reg] for reg in OBSERVED}
        assert (observed, outcome.machine.nzcv) == (record.regs, record.nzcv), record.index
