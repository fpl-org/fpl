"""The canonical text: what llvm-objdump 21.1.8 prints for the program's bytes."""

from hypothesis import given
from hypothesis import strategies as st

from fpl.asm.riscv.model import I, Instr, OpI, OpR, OpStore, OpUpper, Program, R, Reg, Store, Upper
from fpl.asm.riscv.text import print_program

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
)

regs = st.sampled_from(Reg)
instructions: st.SearchStrategy[Instr] = st.one_of(
    st.builds(R, st.sampled_from(OpR), regs, regs, regs),
    st.builds(I, st.sampled_from(OpI), regs, regs, st.integers()),
    st.builds(Upper, st.sampled_from(OpUpper), regs, st.integers()),
    st.builds(Store, st.sampled_from(OpStore), regs, regs, st.integers()),
)
programs = st.lists(instructions, max_size=20).map(tuple)


def test_the_printer_prints_what_llvm_objdump_prints() -> None:
    program = tuple(instr for instr, _ in GOLDEN)
    assert print_program(program) == "".join(f"\t{line}\n" for _, line in GOLDEN)


@given(programs, programs)
def test_the_text_of_a_program_is_the_text_of_its_parts(p: Program, q: Program) -> None:
    """The printer is total, one line per instruction, and prints each on its own."""
    assert print_program(p + q) == print_program(p) + print_program(q)
    assert print_program(p).count("\n") == len(p)
