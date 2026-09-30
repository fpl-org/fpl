"""print_program and parse_program: one canonical line per item, and back."""

import pytest
from aarch64_strategies import bases, programs, witnesses
from hypothesis import example, given
from hypothesis import strategies as st

from fpl.asm.aarch64 import model
from fpl.asm.aarch64.alias import preferred
from fpl.asm.aarch64.model import (
    AddSubExtended,
    Adr,
    Bitfield,
    Branch,
    BranchCond,
    BranchReg,
    CompareBranch,
    Cond,
    Extend,
    Instr,
    Label,
    LoadStore,
    LoadStoreUnscaled,
    LogicalImm,
    Mode,
    MoveWide,
    MulAdd,
    MulLong,
    Offset,
    OpAddSub,
    OpBitfield,
    OpBranch,
    OpBranchReg,
    OpCompareBranch,
    OpLoadStore,
    OpLoadStoreUnscaled,
    OpLogicalImm,
    OpMoveWide,
    OpMulAdd,
    OpMulLong,
    OpPair,
    OpTestBranch,
    Pair,
    PostIndex,
    PreIndex,
    Program,
    Reg,
    RegOffset,
    Width,
)
from fpl.asm.aarch64.text import ParseError, parse_program, print_program

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


# Shapes the strategies draw rarely, pinned: every control transfer, both register widths
# of tbz, the one register offset that prints bare, and the width's own extend next to sp
# (`lsl`, or nothing at #0, where cmn with sp must read back as extended), a long multiply
# in base form, an unscaled load, and every addressing mode of a load and a pair.
# TestBranch goes through `model` so pytest does not collect it.
L0 = Label(".L0")
PINNED: Program = (
    AddSubExtended(OpAddSub.ADD, Width.W64, Reg.SP, Reg.X1, Reg.X2, Extend.UXTX, 2),
    AddSubExtended(OpAddSub.ADD, Width.W32, Reg.X1, Reg.SP, Reg.X2, Extend.UXTW, 0),
    AddSubExtended(OpAddSub.ADDS, Width.W32, Reg.ZR, Reg.SP, Reg.ZR, Extend.UXTW, 0),
    MulLong(OpMulLong.SMADDL, Reg.X1, Reg.X2, Reg.X3, Reg.X4),
    LoadStoreUnscaled(OpLoadStoreUnscaled.LDUR_X, Reg.X1, Reg.SP, -3),
    LoadStore(OpLoadStore.LDRB, Reg.X1, Offset(Reg.X2, 0)),
    LoadStore(OpLoadStore.LDRB, Reg.X1, PreIndex(Reg.X2, -1)),
    LoadStore(OpLoadStore.LDRB, Reg.X1, PostIndex(Reg.X2, 1)),
    *(Pair(OpPair.STP, Width.W64, Reg.X1, Reg.X2, Reg.SP, 16, mode) for mode in Mode),
    Branch(OpBranch.B, L0),
    Branch(OpBranch.BL, L0),
    BranchCond(Cond.EQ, L0),
    CompareBranch(OpCompareBranch.CBZ, Width.W32, Reg.X1, L0),
    model.TestBranch(OpTestBranch.TBZ, Reg.X1, 3, L0),
    model.TestBranch(OpTestBranch.TBNZ, Reg.X1, 40, L0),
    Adr(Reg.X2, L0),
    BranchReg(OpBranchReg.BR, Reg.X2),
    LoadStore(OpLoadStore.LDRB, Reg.X1, RegOffset(Reg.X2, Reg.X3, Extend.UXTX, s=False)),
    LogicalImm(OpLogicalImm.ORR, Width.W64, Reg.X0, Reg.ZR, 0xFFFFFFFFFFFEFFFF),
    L0,
)


@example(PINNED)
@given(programs())
def test_parse_after_print_is_the_identity(program: Program) -> None:
    """[law: parse-print-identity] parse_program(print_program(p)) == p for every program the
    valid strategies draw, labels included."""
    assert parse_program(print_program(program)) == program


def test_every_row_and_base_form_reads_back() -> None:
    """Each alias row's witness and each class's base form parse back from their lines."""
    drawn = witnesses() + bases()
    assert parse_program(print_program(drawn)) == drawn


@pytest.mark.parametrize(
    "line",
    [
        "\tldrh\tw1, [x2, x3, lsl #0]",  # S = 0 prints [x2, x3]; lsl #0 is not canonical
        "\tadd\tx1, x2, x3, lsl #0",  # the default shift is dropped
        "\tmovz\tx1, #1",  # the mov alias is preferred
        "\tmov\tx1, #65537",  # two nonzero 16-bit chunks and no bitmask: no mov reads it
        "\tret\tx30",  # ret's default register is not printed
        "\tmov x1, x2",  # a space, not a tab, after the mnemonic
        "\tfoo\tx1",  # no such mnemonic
        "\tadd\tx1, x31, x2",  # no such register
        "\tnop\t",  # an empty operand field
        "b .L0:",  # not a label definition
    ],
)
def test_a_line_not_in_canonical_form_is_refused_with_its_number(line: str) -> None:
    with pytest.raises(ParseError) as refused:
        parse_program(f"\tnop\n.L0:\n{line}\n")
    assert refused.value.line == 3
    assert str(refused.value).startswith("line 3: ")


@pytest.mark.parametrize(
    ("line", "instr"),
    [
        ("\tmovz\tx1, #65536", MoveWide(OpMoveWide.MOVZ, Width.W64, Reg.X1, 65536, 0)),
        ("\tmovz\tw1, #1, lsl #32", MoveWide(OpMoveWide.MOVZ, Width.W32, Reg.X1, 1, 2)),
        ("\tubfm\tx1, x2, #64, #0", Bitfield(OpBitfield.UBFM, Width.W64, Reg.X1, Reg.X2, 64, 0)),
        (
            "\tldrb\tw1, [x2, x3, uxtb #0]",
            LoadStore(OpLoadStore.LDRB, Reg.X1, RegOffset(Reg.X2, Reg.X3, Extend.UXTB, s=True)),
        ),
    ],
)
def test_base_forms_with_out_of_range_fields_are_read(line: str, instr: Instr) -> None:
    """No alias row matches an out-of-range field, so its base form prints and parses."""
    assert parse_program(line + "\n") == (instr,)
