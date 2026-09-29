"""The canonical text of a program: what llvm-objdump prints for its bytes, address removed.

The target is `llvm-objdump -d -M no-aliases -M numeric --no-print-imm-hex --mattr=+m`, LLVM
21.1.8: one line per instruction, `"\t{op}\t{operands}\n"`. The printer is total: it prints
any value the model holds, out-of-range immediates included, so the checker and the oracle can
both refuse the same text.
"""

from fpl.asm.riscv.model import Program


def print_program(program: Program) -> str:
    """The program's text, one `\\t{op}\\t{operands}\\n` line per instruction, in order."""
    return "".join(f"\t{instr.op}\t{instr.operands()}\n" for instr in program)
