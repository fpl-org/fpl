"""The canonical text of a program: what llvm-objdump prints for its bytes (design section 3).

`print_program` prints one line per item: `\t{mnemonic}\t{operands}` for an instruction in
its preferred disassembly (`alias.preferred`), `\t{mnemonic}` when it has no operands (`nop`,
`ret`), and `{name}:` for a label; every line ends in a newline.

`parse_program` reads exactly that form back. For each line it tries every reading of the
mnemonic (alias rows and base forms, `alias.CANDIDATES`) and keeps the one whose reprint is
the line, so anything not in canonical form, such as `ldrh w1, [x2, x3, lsl #0]` for the
S = 0 form, is refused with its line number.
"""

import re
from dataclasses import dataclass
from typing import override

from fpl.asm.aarch64.alias import CANDIDATES, Operands, preferred
from fpl.asm.aarch64.model import Instr, Item, Label, Program

LABEL = re.compile(r"(\S+):")
INSTRUCTION = re.compile(r"\t(\S+)(?:\t(.+))?")


@dataclass(frozen=True, slots=True)
class ParseError(Exception):
    """A line that is not in canonical form, with its 1-based number."""

    line: int
    message: str

    @override
    def __str__(self) -> str:
        """`line N: message`."""
        return f"line {self.line}: {self.message}"


def line(item: Item) -> str:
    """The text of one item, without its newline."""
    if isinstance(item, Label):
        return f"{item.name}:"
    mnemonic, operands = preferred(item)
    return f"\t{mnemonic}\t{operands}" if operands else f"\t{mnemonic}"


def print_program(program: Program) -> str:
    """The program's text, one newline-terminated line per item."""
    return "".join(line(item) + "\n" for item in program)


def instruction(text: str) -> Instr | None:
    """The instruction whose canonical line is `text`, if there is one."""
    found = INSTRUCTION.fullmatch(text)
    if found is None:
        return None
    mnemonic, operands = found.group(1), found.group(2) or ""
    for build in CANDIDATES.get(mnemonic, ()):
        try:
            instr = build(Operands.of(operands))
        except (LookupError, ValueError, TypeError):
            continue
        if line(instr) == text:
            return instr
    return None


def item(number: int, text: str) -> Item:
    """The item on line `number`; ParseError when the line is not in canonical form."""
    label = LABEL.fullmatch(text)
    if label:
        return Label(label.group(1))
    instr = instruction(text)
    if instr is None:
        raise ParseError(number, f"not an instruction in canonical form: {text!r}")
    return instr


def parse_program(text: str) -> Program:
    """The program `print_program` printed as `text`; ParseError names the first line that
    is not in canonical form."""
    return tuple(item(number, line) for number, line in enumerate(text.splitlines(), 1))
