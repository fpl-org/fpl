"""The canonical text of a program: what llvm-objdump prints for its bytes (design section 3).

`print_program` prints one line per item: `\t{mnemonic}\t{operands}` for an instruction, in
its preferred disassembly (`alias.preferred`), and `{name}:` for a label; every line ends in
a newline.
"""

from fpl.asm.aarch64.alias import preferred
from fpl.asm.aarch64.model import Item, Label, Program


def line(item: Item) -> str:
    """The text of one item, without its newline."""
    if isinstance(item, Label):
        return f"{item.name}:"
    mnemonic, operands = preferred(item)
    return f"\t{mnemonic}\t{operands}"


def print_program(program: Program) -> str:
    """The program's text, one newline-terminated line per item."""
    return "".join(line(item) + "\n" for item in program)
