"""The canonical text: what llvm-objdump 21.1.8 prints for the program's bytes, and back."""

import pytest
from hypothesis import example, given
from hypothesis import strategies as st
from riscv_strategies import instructions

from fpl.asm.riscv.model import (
    Access,
    Bare,
    Branch,
    Fence,
    I,
    Instr,
    Item,
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
from fpl.asm.riscv.text import SHAPES, ParseError, line, parse_program, pattern, print_program

# Every op and every register at least once, with the immediates' edges. The right-hand
# lines are copied from `llvm-objdump -d -M no-aliases -M numeric --no-print-imm-hex
# --mattr=+m --no-show-raw-insn` of `llvm-mc -triple=riscv64 -mattr=+m,-relax` on this
# program, address column removed.
GOLDEN: tuple[tuple[Instr, str], ...] = (
    (R(OpR.ADD, Reg.X0, Reg.X1, Reg.X2), "add\tx0, x1, x2"),
    (R(OpR.SUB, Reg.X3, Reg.X4, Reg.X5), "sub\tx3, x4, x5"),
    (R(OpR.SLL, Reg.X6, Reg.X7, Reg.X8), "sll\tx6, x7, x8"),
    (R(OpR.SLT, Reg.X9, Reg.X10, Reg.X11), "slt\tx9, x10, x11"),
    (R(OpR.SLTU, Reg.X12, Reg.X13, Reg.X14), "sltu\tx12, x13, x14"),
    (R(OpR.XOR, Reg.X15, Reg.X16, Reg.X17), "xor\tx15, x16, x17"),
    (R(OpR.SRL, Reg.X18, Reg.X19, Reg.X20), "srl\tx18, x19, x20"),
    (R(OpR.SRA, Reg.X21, Reg.X22, Reg.X23), "sra\tx21, x22, x23"),
    (R(OpR.OR, Reg.X24, Reg.X25, Reg.X26), "or\tx24, x25, x26"),
    (R(OpR.AND, Reg.X27, Reg.X28, Reg.X29), "and\tx27, x28, x29"),
    (R(OpR.ADDW, Reg.X30, Reg.X31, Reg.X0), "addw\tx30, x31, x0"),
    (R(OpR.SUBW, Reg.X1, Reg.X2, Reg.X3), "subw\tx1, x2, x3"),
    (R(OpR.SLLW, Reg.X4, Reg.X5, Reg.X6), "sllw\tx4, x5, x6"),
    (R(OpR.SRLW, Reg.X7, Reg.X8, Reg.X9), "srlw\tx7, x8, x9"),
    (R(OpR.SRAW, Reg.X10, Reg.X11, Reg.X12), "sraw\tx10, x11, x12"),
    (R(OpR.MUL, Reg.X13, Reg.X14, Reg.X15), "mul\tx13, x14, x15"),
    (R(OpR.MULH, Reg.X16, Reg.X17, Reg.X18), "mulh\tx16, x17, x18"),
    (R(OpR.MULHSU, Reg.X19, Reg.X20, Reg.X21), "mulhsu\tx19, x20, x21"),
    (R(OpR.MULHU, Reg.X22, Reg.X23, Reg.X24), "mulhu\tx22, x23, x24"),
    (R(OpR.DIV, Reg.X25, Reg.X26, Reg.X27), "div\tx25, x26, x27"),
    (R(OpR.DIVU, Reg.X28, Reg.X29, Reg.X30), "divu\tx28, x29, x30"),
    (R(OpR.REM, Reg.X31, Reg.X0, Reg.X1), "rem\tx31, x0, x1"),
    (R(OpR.REMU, Reg.X2, Reg.X3, Reg.X4), "remu\tx2, x3, x4"),
    (R(OpR.MULW, Reg.X5, Reg.X6, Reg.X7), "mulw\tx5, x6, x7"),
    (R(OpR.DIVW, Reg.X8, Reg.X9, Reg.X10), "divw\tx8, x9, x10"),
    (R(OpR.DIVUW, Reg.X11, Reg.X12, Reg.X13), "divuw\tx11, x12, x13"),
    (R(OpR.REMW, Reg.X14, Reg.X15, Reg.X16), "remw\tx14, x15, x16"),
    (R(OpR.REMUW, Reg.X17, Reg.X18, Reg.X19), "remuw\tx17, x18, x19"),
    (I(OpI.ADDI, Reg.X5, Reg.X9, -2048), "addi\tx5, x9, -2048"),
    (I(OpI.SLTI, Reg.X7, Reg.X11, 2047), "slti\tx7, x11, 2047"),
    (I(OpI.SLTIU, Reg.X9, Reg.X13, -1), "sltiu\tx9, x13, -1"),
    (I(OpI.XORI, Reg.X11, Reg.X15, 0), "xori\tx11, x15, 0"),
    (I(OpI.ORI, Reg.X13, Reg.X17, 1), "ori\tx13, x17, 1"),
    (I(OpI.ANDI, Reg.X15, Reg.X19, -2), "andi\tx15, x19, -2"),
    (I(OpI.ADDIW, Reg.X17, Reg.X21, 5), "addiw\tx17, x21, 5"),
    (Upper(OpUpper.LUI, Reg.X1, 1048575), "lui\tx1, 1048575"),
    (Upper(OpUpper.AUIPC, Reg.X31, 0), "auipc\tx31, 0"),
    (Store(OpStore.SB, Reg.X6, Reg.X5, -2048), "sb\tx6, -2048(x5)"),
    (Store(OpStore.SH, Reg.X7, Reg.X8, 2047), "sh\tx7, 2047(x8)"),
    (Store(OpStore.SW, Reg.X9, Reg.X10, 0), "sw\tx9, 0(x10)"),
    (Store(OpStore.SD, Reg.X1, Reg.X2, -8), "sd\tx1, -8(x2)"),
    (Shift(OpShift.SLLI, Reg.X1, Reg.X2, 63), "slli\tx1, x2, 63"),
    (Shift(OpShift.SRLI, Reg.X3, Reg.X4, 0), "srli\tx3, x4, 0"),
    (Shift(OpShift.SRAI, Reg.X5, Reg.X6, 32), "srai\tx5, x6, 32"),
    (Shift(OpShift.SLLIW, Reg.X7, Reg.X8, 31), "slliw\tx7, x8, 31"),
    (Shift(OpShift.SRLIW, Reg.X9, Reg.X10, 1), "srliw\tx9, x10, 1"),
    (Shift(OpShift.SRAIW, Reg.X11, Reg.X12, 0), "sraiw\tx11, x12, 0"),
    (Load(OpLoad.LB, Reg.X1, Reg.X2, -2048), "lb\tx1, -2048(x2)"),
    (Load(OpLoad.LH, Reg.X3, Reg.X4, 2047), "lh\tx3, 2047(x4)"),
    (Load(OpLoad.LW, Reg.X5, Reg.X6, 0), "lw\tx5, 0(x6)"),
    (Load(OpLoad.LBU, Reg.X7, Reg.X8, 1), "lbu\tx7, 1(x8)"),
    (Load(OpLoad.LHU, Reg.X9, Reg.X10, -1), "lhu\tx9, -1(x10)"),
    (Load(OpLoad.LWU, Reg.X11, Reg.X12, 8), "lwu\tx11, 8(x12)"),
    (Load(OpLoad.LD, Reg.X1, Reg.X2, -8), "ld\tx1, -8(x2)"),
    (Jalr(Reg.X1, Reg.X2, -4), "jalr\tx1, -4(x2)"),
    (Jalr(Reg.X0, Reg.X1, 0), "jalr\tx0, 0(x1)"),
    (Fence(Access.I | Access.O | Access.R | Access.W, ~Access(0)), "fence\tiorw, iorw"),
    (Fence(Access(0), Access(0)), "fence\t0, 0"),
    (Fence(Access.R, Access.I | Access.W), "fence\tr, iw"),
    (Fence(Access.O, Access.R | Access.W), "fence\to, rw"),
    (Bare(OpBare.FENCE_TSO), "fence.tso"),
    (Bare(OpBare.ECALL), "ecall"),
    (Bare(OpBare.EBREAK), "ebreak"),
)
# Control transfers and labels: objdump prints the resolved address where the printer prints the
# label's name, so these lines are the printer's; control-targets-agree checks the addresses.
CONTROL: tuple[tuple[Item, str], ...] = (
    (Branch(OpBranch.BEQ, Reg.X1, Reg.X2, Label(".L1")), "\tbeq\tx1, x2, .L1"),
    (Branch(OpBranch.BNE, Reg.X3, Reg.X4, Label(".L1")), "\tbne\tx3, x4, .L1"),
    (Branch(OpBranch.BLT, Reg.X5, Reg.X6, Label(".L1")), "\tblt\tx5, x6, .L1"),
    (Branch(OpBranch.BGE, Reg.X7, Reg.X8, Label(".L1")), "\tbge\tx7, x8, .L1"),
    (Branch(OpBranch.BLTU, Reg.X9, Reg.X10, Label(".L_x9")), "\tbltu\tx9, x10, .L_x9"),
    (Branch(OpBranch.BGEU, Reg.X11, Reg.X12, Label(".L_x9")), "\tbgeu\tx11, x12, .L_x9"),
    (Jal(Reg.X1, Label(".L1")), "\tjal\tx1, .L1"),
    (Label(".L1"), ".L1:"),
    (Label(".L_x9"), ".L_x9:"),
)

# Any value the model holds, immediates unbounded; label names in the checker's form.
regs = st.sampled_from(Reg)
ints = st.integers()
labels = st.from_regex(r"\.L[A-Za-z0-9_]+", fullmatch=True).map(Label)
accesses = st.integers(0, 15).map(Access)
items: st.SearchStrategy[Item] = st.one_of(
    st.builds(R, st.sampled_from(OpR), regs, regs, regs),
    st.builds(I, st.sampled_from(OpI), regs, regs, ints),
    st.builds(Shift, st.sampled_from(OpShift), regs, regs, ints),
    st.builds(Upper, st.sampled_from(OpUpper), regs, ints),
    st.builds(Load, st.sampled_from(OpLoad), regs, regs, ints),
    st.builds(Store, st.sampled_from(OpStore), regs, regs, ints),
    st.builds(Branch, st.sampled_from(OpBranch), regs, regs, labels),
    st.builds(Jal, regs, labels),
    st.builds(Jalr, regs, regs, ints),
    st.builds(Fence, accesses, accesses),
    st.builds(Bare, st.sampled_from(OpBare)),
    labels,
)
programs = st.lists(st.one_of(items, instructions()), max_size=20).map(tuple)
# Edits that leave no line in canonical form, whatever the line was.
BREAKS = (" {}", "{} ", "\t{}", "{}\t", "{},", "#{}")
# Lines the parser refuses although an assembler might read them.
REFUSED = (
    "\taddi\tx1, x2, -0",
    "\taddi\tx1, x2, 007",
    "\taddi\tx1, x2, +1",
    "\taddi\tx1, x2, 0x10",
    "\taddi\tx01, x2, 1",
    "\taddi\ta0, x2, 1",
    "\taddi\tx32, x2, 1",
    "\taddi\tx1,x2,1",
    "\tADDI\tx1, x2, 1",
    "\tli\tx1, 1",
    "\tpause",
    "\tecall\t",
    "\tfence\tri, w",
    "\tfence\t, w",
    "\tbeq\tx1, x2, foo",
    "L1:",
    ".L-1:",
    "",
)


def test_the_printer_prints_what_llvm_objdump_prints() -> None:
    program = tuple(instr for instr, _ in GOLDEN)
    assert print_program(program) == "".join(f"\t{line}\n" for _, line in GOLDEN)


def test_control_transfers_print_their_label_names() -> None:
    program = tuple(item for item, _ in CONTROL)
    assert print_program(program) == "".join(f"{line}\n" for _, line in CONTROL)


@given(programs, programs)
def test_the_text_of_a_program_is_the_text_of_its_parts(p: Program, q: Program) -> None:
    """The printer is total, one line per item, and prints each on its own."""
    assert print_program(p + q) == print_program(p) + print_program(q)
    assert print_program(p).count("\n") == len(p)


@given(programs, st.integers(0), st.sampled_from(BREAKS))
def test_parsing_a_printed_program_gives_it_back(program: Program, at: int, edit: str) -> None:
    """[law: parse-print-identity] parse after print is the identity; any other line is refused.

    For every program, valid or not, `parse_program(print_program(p)) == p`; one line of the
    text edited out of canonical form is a `ParseError` naming that line.
    """
    text = print_program(program)
    assert parse_program(text) == program
    lines = text.splitlines() or ["\tecall"]
    index = at % len(lines)
    lines[index] = edit.format(lines[index])
    with pytest.raises(ParseError) as error:
        parse_program("".join(f"{line}\n" for line in lines))
    assert error.value.line == index + 1


@pytest.mark.parametrize("line", REFUSED)
def test_a_line_an_assembler_might_read_is_still_refused(line: str) -> None:
    with pytest.raises(ParseError, match="line 2: not in canonical form"):
        parse_program(f"\tecall\n{line}\n")


def test_text_without_its_last_newline_is_refused() -> None:
    with pytest.raises(ParseError, match="line 2: the text does not end with a newline"):
        parse_program("\tecall\n\tecall")


@given(instructions())
@example(Bare(OpBare.ECALL))
def test_the_pattern_of_a_mnemonic_and_its_shape_matches_the_line_printed_for_it(
    instr: Instr,
) -> None:
    """The parser's table is built at import, where mutation testing cannot reach it.

    The explicit operand-free example makes the empty-shape branch run on every call, not only
    when the draw happens to hold one; a mutant there survived a mutation run without it.
    """
    text = line(instr)
    assert pattern(text.split("\t")[1], SHAPES[type(instr)]).fullmatch(text)
