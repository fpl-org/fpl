"""print_program: one line per item, instructions in their preferred disassembly."""

from hypothesis import given
from hypothesis import strategies as st

from fpl.asm.aarch64.alias import preferred
from fpl.asm.aarch64.model import Label, MoveWide, MulAdd, OpMoveWide, OpMulAdd, Reg, Width
from fpl.asm.aarch64.text import print_program

regs = st.sampled_from(Reg)
widths = st.sampled_from(Width)
imm16s = st.integers(0, 0xFFFF)
items = st.one_of(
    st.builds(Label, st.from_regex(r"\.L[A-Za-z0-9_]+", fullmatch=True)),
    st.builds(MoveWide, st.sampled_from(OpMoveWide), widths, regs, imm16s, st.integers(0, 3)),
    st.builds(MulAdd, st.sampled_from(OpMulAdd), widths, regs, regs, regs, regs),
)


@given(st.lists(items).map(tuple))
def test_one_line_per_item(program: tuple[Label | MoveWide | MulAdd, ...]) -> None:
    """Each item is one newline-terminated line: `name:` or `\\tmnemonic\\toperands`."""
    text = print_program(program)
    assert text.endswith("\n") or not program
    lines = text.splitlines()
    assert len(lines) == len(program)
    for item, got in zip(program, lines, strict=True):
        want = f"{item.name}:" if isinstance(item, Label) else "\t{}\t{}".format(*preferred(item))
        assert got == want


def test_the_smoke_block_prints_as_llvm_objdump_does() -> None:
    block = (
        MoveWide(OpMoveWide.MOVZ, Width.W64, Reg.X0, 6, 0),
        MoveWide(OpMoveWide.MOVZ, Width.W64, Reg.X1, 7, 0),
        MulAdd(OpMulAdd.MADD, Width.W64, Reg.X0, Reg.X0, Reg.X1, Reg.ZR),
    )
    assert print_program(block) == "\tmov\tx0, #6\n\tmov\tx1, #7\n\tmul\tx0, x0, x1\n"
