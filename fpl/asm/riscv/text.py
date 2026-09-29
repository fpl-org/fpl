"""The canonical text of a program: what llvm-objdump prints for its bytes, address removed.

The target is `llvm-objdump -d -M no-aliases -M numeric --no-print-imm-hex --mattr=+m`, LLVM
21.1.8: one line per item, `"\t{op}\t{operands}\n"`, `"\t{op}\n"` for `Bare`, `"{name}:\n"`
for a label. Registers print as `x<n>`, immediates in decimal, `lui`/`auipc` immediates as the
unsigned 20-bit field, a fence set in `iorw` order or `0` when empty. A branch or jump prints
its label's name where objdump prints the resolved address.

The printer is total: it prints any value the model holds, out-of-range immediates included, so
the checker and the oracle can both refuse the same text.
"""

from typing import assert_never

from fpl.asm.riscv.model import (
    Access,
    Bare,
    Branch,
    Fence,
    I,
    Item,
    Jal,
    Jalr,
    Label,
    Load,
    Program,
    R,
    Reg,
    Shift,
    Store,
    Upper,
)

# The fence set's letters in printed order, each with its bit.
ACCESS = {"i": Access.I, "o": Access.O, "r": Access.R, "w": Access.W}


def x(reg: Reg) -> str:
    """A register by number: `x10`, never `a0`."""
    return f"x{reg.value}"


def access(bits: Access) -> str:
    """A fence set in `iorw` order, `0` when empty."""
    return "".join(letter for letter, bit in ACCESS.items() if bit in bits) or "0"


def computational(instr: R | I | Shift | Upper) -> str:
    """The operands of the register and immediate forms."""
    match instr:
        case R():
            return f"{x(instr.rd)}, {x(instr.rs1)}, {x(instr.rs2)}"
        case I():
            return f"{x(instr.rd)}, {x(instr.rs1)}, {instr.imm}"
        case Shift():
            return f"{x(instr.rd)}, {x(instr.rs1)}, {instr.shamt}"
        case Upper():
            return f"{x(instr.rd)}, {instr.imm}"
        case _:
            assert_never(instr)


def addressed(instr: Load | Store | Jalr) -> str:
    """The operands of the forms that address `offset(rs1)`."""
    match instr:
        case Load():
            return f"{x(instr.rd)}, {instr.offset}({x(instr.rs1)})"
        case Store():
            return f"{x(instr.rs2)}, {instr.offset}({x(instr.rs1)})"
        case Jalr():
            return f"{x(instr.rd)}, {instr.offset}({x(instr.rs1)})"
        case _:
            assert_never(instr)


def named(instr: Branch | Jal | Fence) -> str:
    """The operands of the forms that print a name: a label, or a fence set."""
    match instr:
        case Branch():
            return f"{x(instr.rs1)}, {x(instr.rs2)}, {instr.target.name}"
        case Jal():
            return f"{x(instr.rd)}, {instr.target.name}"
        case Fence():
            return f"{access(instr.pred)}, {access(instr.succ)}"
        case _:
            assert_never(instr)


def line(item: Item) -> str:
    """The line of one item, without its newline."""
    match item:
        case Label():
            return f"{item.name}:"
        case Bare():
            return f"\t{item.op}"
        case R() | I() | Shift() | Upper():
            return f"\t{item.op}\t{computational(item)}"
        case Load() | Store() | Jalr():
            return f"\t{item.op}\t{addressed(item)}"
        case Branch() | Jal() | Fence():
            return f"\t{item.op}\t{named(item)}"
        case _:
            assert_never(item)


def print_program(program: Program) -> str:
    """The program's text: each item's line and a newline, in order."""
    return "".join(f"{line(item)}\n" for item in program)
