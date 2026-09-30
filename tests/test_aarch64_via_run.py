"""Oracle tests on the machine itself: natively on Darwin, under qemu-aarch64 on Linux."""

import pytest
from aarch64_frame import RECORD, Block, frame, records
from aarch64_oracle import assemble, execute, link, toolchain
from hypothesis import given
from hypothesis import strategies as st

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
