"""The canonical text of a program: what llvm-objdump prints for its bytes, address removed.

The target is `llvm-objdump -d -M no-aliases -M numeric --no-print-imm-hex --mattr=+m`, LLVM
21.1.8: one line per item, `"\t{op}\t{operands}\n"`, `"\t{op}\n"` for `Bare`, `"{name}:\n"`
for a label. Registers print as `x<n>`, immediates in decimal, `lui`/`auipc` immediates as the
unsigned 20-bit field, a fence set in `iorw` order or `0` when empty. A branch or jump prints
its label's name where objdump prints the resolved address.

The printer is total: it prints any value the model holds, out-of-range immediates included, so
the checker and the oracle can both refuse the same text.

The parser reads exactly that text back and nothing else: no aliases, no ABI register names, no
hex, no `+`, `-0` or leading zeros, no spacing but the printer's, a label name only in the form
`.L[A-Za-z0-9_]+`, and a newline after every line. Any other line is a `ParseError` naming its
1-based line number. Print and parse live in this one module because they are one law: parsing
a printed program gives the program back.
"""

import re
from collections.abc import Callable
from enum import StrEnum
from string import Formatter
from typing import Any, assert_never

from fpl.asm.riscv.model import (
    CLASSES,
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
    Program,
    R,
    Reg,
    Shift,
    Store,
    Upper,
    mnemonics,
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


class ParseError(Exception):
    """A line of text that is not in canonical form, by its 1-based number."""

    def __init__(self, line: int, message: str) -> None:
        """Say which line, and what is wrong with it."""
        super().__init__(f"line {line}: {message}")
        self.line = line


def fence_set(text: str) -> Access:
    """The fence set a canonical `iorw`-ordered text (or `0`) names."""
    return Access(sum(ACCESS.get(letter, 0) for letter in text))


# Each form's operands as the printer writes them; the parser reads each field by its name.
SHAPES: dict[type[Instr], str] = {
    R: "{rd}, {rs1}, {rs2}",
    I: "{rd}, {rs1}, {imm}",
    Shift: "{rd}, {rs1}, {shamt}",
    Upper: "{rd}, {imm}",
    Load: "{rd}, {offset}({rs1})",
    Store: "{rs2}, {offset}({rs1})",
    Branch: "{rs1}, {rs2}, {target}",
    Jal: "{rd}, {target}",
    Jalr: "{rd}, {offset}({rs1})",
    Fence: "{pred}, {succ}",
    Bare: "",
}
REG = r"x(?:[12]?[0-9]|3[01])"
IMM = r"0|-?[1-9][0-9]*"
NAME = r"\.L[A-Za-z0-9_]+"
SET = r"0|(?=[iorw])i?o?r?w?"
# A field name's canonical text and the value it reads as.
FIELDS: dict[str, tuple[str, Callable[[str], Any]]] = {
    "rd": (REG, lambda text: Reg(int(text[1:]))),
    "rs1": (REG, lambda text: Reg(int(text[1:]))),
    "rs2": (REG, lambda text: Reg(int(text[1:]))),
    "imm": (IMM, int),
    "shamt": (IMM, int),
    "offset": (IMM, int),
    "target": (NAME, Label),
    "pred": (SET, fence_set),
    "succ": (SET, fence_set),
}
LABEL = re.compile(f"({NAME}):")


def pattern(mnemonic: str, shape: str) -> re.Pattern[str]:
    """The one line the printer prints for `mnemonic` with operands of `shape`."""
    operands = "".join(
        re.escape(literal) + (f"(?P<{name}>{FIELDS[name][0]})" if name else "")
        for literal, name, _, _ in Formatter().parse(shape)
    )
    return re.compile(re.escape(f"\t{mnemonic}") + (f"\t{operands}" if shape else ""))


# Each mnemonic's line pattern, its class, and the op to construct it with (none when fixed).
FORMS: dict[str, tuple[re.Pattern[str], type[Instr], dict[str, Any]]] = {
    mnemonic: (
        pattern(mnemonic, SHAPES[form]),
        form,
        {"op": mnemonic} if isinstance(mnemonic, StrEnum) else {},
    )
    for form in CLASSES
    for mnemonic in mnemonics(form)
}


def parse_line(number: int, text: str) -> Item:
    """The item line `number` holds, or a `ParseError` if it is not a printed line."""
    if label := LABEL.fullmatch(text):
        return Label(label[1])
    form = FORMS.get(text.partition("\t")[2].partition("\t")[0])
    found = form[0].fullmatch(text) if form else None
    if form is None or found is None:
        raise ParseError(number, f"not in canonical form: {text!r}")
    _, instr, op = form
    return instr(
        **op, **{name: FIELDS[name][1](value) for name, value in found.groupdict().items()}
    )


def parse_program(text: str) -> Program:
    """The program whose printed text is `text`; the inverse of `print_program`."""
    *lines, tail = text.split("\n")
    if tail:
        raise ParseError(len(lines) + 1, "the text does not end with a newline")
    return tuple(parse_line(number, line) for number, line in enumerate(lines, 1))
