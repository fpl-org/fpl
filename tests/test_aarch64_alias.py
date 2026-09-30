"""The alias rows against their C6.2 conditions: MOV (wide immediate) of MOVZ, MUL of MADD."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fpl.asm.aarch64.alias import ROWS, preferred
from fpl.asm.aarch64.model import MoveWide, MulAdd, OpMoveWide, OpMulAdd, Reg, Width

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


def test_the_divergent_rows_are_those_alias_divergence_names() -> None:
    """The rows whose text follows llvm-objdump, not the C6.2 condition: BFM's bfi (the spec
    prefers BFC) and ORR's mov (the spec's !MoveWidePreferred)."""
    flagged = {
        (row.mnemonic, row.cite.split(" ")[0])
        for rows in ROWS.values()
        for row in rows
        if row.spec_differs
    }
    assert flagged == {("bfi", "C6.2.39"), ("mov", "C6.2.301")}
