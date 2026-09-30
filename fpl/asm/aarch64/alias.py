"""The preferred disassembly (C1.4): which alias, if any, prints a base instruction.

Per class, an ordered table of rows, each an alias the C6.2 page of its base instruction
lists, with the condition under which that alias "is preferred" as the spec states it, plus
the operand ranges the condition assumes: an instruction with an out-of-range field matches
no row and prints in its base form, so the text still carries the value. The first row that
matches wins; none matching, the base form prints.

The rows so far: MOV (wide immediate) for MOVZ and MUL for MADD. The text is llvm-objdump's
(LLVM 21.1.8, default aliases, decimal immediates) where it differs from the spec.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import assert_never

from fpl.asm.aarch64.model import Instr, MoveWide, MulAdd, OpMoveWide, OpMulAdd, Reg


@dataclass(frozen=True, slots=True)
class Row[T: Instr]:
    """One alias of a base page: its mnemonic, when it is preferred, and its operands."""

    mnemonic: str
    when: Callable[[T], bool]
    operands: Callable[[T], str]


def is_mov_wide(instr: MoveWide) -> bool:
    """MOVZ page, MOV (wide immediate): `!(IsZero(imm16) && hw != '00')`, fields in range."""
    in_range = 0 <= instr.imm16 <= 0xFFFF and 0 <= instr.hw < instr.width // 16
    return instr.op is OpMoveWide.MOVZ and in_range and not (instr.imm16 == 0 and instr.hw != 0)


def mov_wide_operands(instr: MoveWide) -> str:
    """`rd, #value`: the value moved, as signed two's-complement decimal at the width."""
    value = instr.imm16 << (16 * instr.hw)
    if value >> (instr.width - 1):
        value -= 1 << instr.width
    return f"{instr.rd.name_at(instr.width)}, #{value}"


def is_mul(instr: MulAdd) -> bool:
    """MADD page, MUL: `Ra == '11111'`, the zero register as accumulator."""
    return instr.op is OpMulAdd.MADD and instr.ra is Reg.ZR


def mul_operands(instr: MulAdd) -> str:
    """`rd, rn, rm`: the MADD operands without the zero accumulator."""
    return ", ".join(reg.name_at(instr.width) for reg in (instr.rd, instr.rn, instr.rm))


MOVE_WIDE: tuple[Row[MoveWide], ...] = (
    Row("mov", is_mov_wide, mov_wide_operands),  # MOVZ, C6.2.285: MOV (wide immediate)
)
MUL_ADD: tuple[Row[MulAdd], ...] = (
    Row("mul", is_mul, mul_operands),  # MADD, C6.2.275: MUL
)


def first[T: Instr](rows: tuple[Row[T], ...], instr: T) -> tuple[str, str]:
    """The first matching row's mnemonic and operands, else the base form's."""
    for row in rows:
        if row.when(instr):
            return row.mnemonic, row.operands(instr)
    return instr.op.value, instr.operands()


def preferred(instr: Instr) -> tuple[str, str]:
    """The mnemonic and operands llvm-objdump prints for `instr`."""
    match instr:
        case MoveWide():
            return first(MOVE_WIDE, instr)
        case MulAdd():
            return first(MUL_ADD, instr)
        case _:
            assert_never(instr)
