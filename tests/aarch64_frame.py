"""Not a test: the fixed frame a batch of blocks runs in, in two flavours, and its decoder.

The frame follows Apple's "Writing ARM64 code for Apple platforms" on both routes: x18 is
never touched, x29 stays a valid frame record, sp moves only by 256 and stays 16-byte aligned.
Per block i it pushes a 256-byte record, stores the block's base address (`adr`) at 240, sets
NZCV by `msr` and the 29 observed registers by `movz`/`movk` IR values to the block's initial
state, runs the block, its labels prefixed `.Lb<i>_`, then stores x0-x17, x19-x28 and x30 at
`8 * j` (j = 0..28), NZCV (`mrs`) at 232 and i at 248. After the last block it writes every
record to stdout, last block first, and exits 0: on Darwin (`_main`, Mach-O) through
libSystem's `_write` and `_exit`, since raw syscalls are not a stable ABI there; on Linux
(`_start`, static ELF) by `svc #0` (write 64, exit 93). The records sit on the stack,
sp-relative, so no line needs a relocation and one text serves both formats. No comments:
Mach-O starts them with `;`, ELF with `//`.

It uses `mrs`/`msr nzcv`, `svc` and a platform ABI, all outside the IR's subset, so it lives
here (hole `frame-home`).
"""

import re
import struct
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass

from fpl.asm.aarch64.model import MoveWide, OpMoveWide, Program, Reg, Width
from fpl.asm.aarch64.text import print_program

RECORD = 256
OBSERVED = (*range(18), *range(19, 29), 30)  # the registers stored, slot j at byte 8 * j
NZCV, BASE, INDEX = 232, 240, 248
FLAGS_AT = 28  # NZCV is bits 31..28 of the `mrs`/`msr` value (C5.2.11)
ENTRY = {"Darwin": "_main", "Linux": "_start"}
WRITE_AND_EXIT = {
    "Darwin": "\tbl\t_write\n\tmov\tx0, #0\n\tbl\t_exit\n",
    "Linux": "\tmov\tx8, #64\n\tsvc\t#0\n\tmov\tx0, #0\n\tmov\tx8, #93\n\tsvc\t#0\n",
}
LOCAL = re.compile(r"\.L(\w+)")


class RunError(Exception):
    """The run did not exit 0 with one well-formed record per block."""


@dataclass(frozen=True, slots=True)
class Block:
    """One block of a batch: x0..x30 as the evaluator's `Machine` holds them (the frame sets
    only the observed 29; x18 and x29 are the platform's), four NZCV bits, and the program."""

    regs: tuple[int, ...]
    nzcv: int
    program: Program


@dataclass(frozen=True, slots=True)
class Record:
    """What one block left behind: the observed registers by number, NZCV as four bits, the
    block's base address, and the block's index."""

    regs: dict[int, int]
    nzcv: int
    base: int
    index: int


def moves(reg: Reg, value: int) -> tuple[MoveWide, ...]:
    """`reg` set to the 64-bit `value`: movz of the low halfword, movk of each other nonzero."""
    halves = [(value >> (16 * hw)) & 0xFFFF for hw in range(4)]
    high = [
        MoveWide(OpMoveWide.MOVK, Width.W64, reg, half, hw)
        for hw, half in enumerate(halves)
        if hw and half
    ]
    return (MoveWide(OpMoveWide.MOVZ, Width.W64, reg, halves[0], 0), *high)


def setup(block: Block) -> str:
    """NZCV by `msr` through x0, then the observed registers, x0 among them."""
    flags = print_program(moves(Reg.X0, block.nzcv << FLAGS_AT))
    registers = tuple(move for reg in OBSERVED for move in moves(Reg(reg), block.regs[reg]))
    return f"{flags}\tmsr\tnzcv, x0\n{print_program(registers)}"


def placed(index: int, block: Block) -> str:
    """Block `index` inside its record: push, base, initial state, the block, the stores."""
    label = f".Lb{index}"
    text = LOCAL.sub(rf"{label}_\1", print_program(block.program))
    stores = "".join(f"\tstr\tx{reg}, [sp, #{8 * j}]\n" for j, reg in enumerate(OBSERVED))
    return (
        f"\tsub\tsp, sp, #{RECORD}\n\tadr\tx0, {label}\n\tstr\tx0, [sp, #{BASE}]\n"
        f"{setup(block)}{label}:\n{text}{stores}"
        f"\tmrs\tx0, nzcv\n\tstr\tx0, [sp, #{NZCV}]\n"
        f"\tmov\tx0, #{index}\n\tstr\tx0, [sp, #{INDEX}]\n"
    )


def frame(system: str, blocks: Sequence[Block]) -> str:
    """The whole program for `system`'s route, the `blocks` run in order."""
    entry = ENTRY[system]
    size = RECORD * len(blocks)
    return (
        f"\t.text\n\t.globl\t{entry}\n\t.p2align\t2\n{entry}:\n"
        "\tstp\tx29, x30, [sp, #-16]!\n\tmov\tx29, sp\n"
        + "".join(placed(index, block) for index, block in enumerate(blocks))
        + f"\tmov\tx0, #1\n\tmov\tx1, sp\n\tmov\tx2, #{size}\n"
        + WRITE_AND_EXIT[system]
    )


def records(done: subprocess.CompletedProcess[bytes], count: int) -> tuple[Record, ...]:
    """The `count` records the run wrote, first block first, or a `RunError` showing it: a
    nonzero exit, a short or long output, an index out of order, or an `mrs` value with bits
    outside NZCV."""
    shown = f"exit {done.returncode}, stderr {done.stderr!r}, stdout {done.stdout.hex()}"
    if done.returncode != 0 or len(done.stdout) != RECORD * count:
        raise RunError(f"expected exit 0 and {count} records of {RECORD} bytes: {shown}")
    found: list[Record] = []
    for index in range(count):
        at = RECORD * (count - 1 - index)
        words = struct.unpack_from("<32Q", done.stdout, at)
        flags, base, number = words[29:32]
        if number != index or flags & ~(0xF << FLAGS_AT):
            raise RunError(f"record {index}: index {number}, mrs nzcv {flags:#x}: {shown}")
        regs = dict(zip(OBSERVED, words, strict=False))
        found.append(Record(regs, flags >> FLAGS_AT, base, number))
    return tuple(found)
