"""Not a test: the QEMU virt frames, the text printed programs run inside, and their decoder.

A frame is Zicsr and privileged text outside the IR, so it lives here as text, not in
`fpl.asm.riscv` (hole `virt-frame-home`). Two frames:

- `framed`, the minimal one: `_start` before one program and the spin after it. The program
  itself reports, by bytes stored to the UART's transmit register and a word stored to the test
  device, whose low half 0x3333 asks QEMU to exit with the high half as its status.
- `batch`, the frame for many blocks in one boot (design section 7). `_start` points `mtvec` at
  the trap handler; then, per block i, `tp` (x4) takes the address of the block's record, x1..x31
  but x4 are loaded from it, the block runs from the symbol `block<i>` (its labels relabelled
  `.Lb<i>_`), x1..x31 are stored to the record's save area, and the UART gets `R` and the save
  area's 248 bytes. After the last block the test device gets 0x5555 (exit 0) and the hart spins.
  A trap anywhere in block i sends `T`, `mcause` and `mepc` (8 bytes each, little-endian) and
  resumes after block i's report, where the next block reloads every register.

The frame uses x4 as its own and the blocks touch neither x3 nor x4 (hole
`harness-registers`); x4's slot in a report is the record's address, not a block's value.
`decode` turns the UART's bytes back into one `Report` per block.
"""

import struct
from collections.abc import Sequence
from dataclasses import dataclass, replace

from fpl.asm.riscv.model import Branch, Item, Jal, Label, Program
from fpl.asm.riscv.text import print_program

UART = 0x1000_0000  # the 16550 on virt: a byte stored here is a byte on -serial stdio
TEST_DEVICE = 0x10_0000  # sifive_test on virt
HEAD = "\t.text\n\t.globl\t_start\n_start:\n"
# QEMU finishes asynchronously after the test-device store: without the spin the hart runs on
# into whatever follows, traps, and a second report may win (probe log 5).
SPIN = "\tjal\tx0, .\n"


def framed(program_text: str) -> str:
    """`program_text` between `_start` and the spin: a whole source for `assemble`."""
    return HEAD + program_text + SPIN


SLOTS = 31  # x1..x31, x4's slot included: 248 bytes
SAVE = 8 * SLOTS  # a record's save area follows its 31 initial values
RESUME = 2 * SAVE  # then the address a trap in the block resumes at
EXIT_0 = 0x5555  # the test device's pass code: QEMU exits 0


@dataclass(frozen=True, slots=True)
class Block:
    """A program and the values x1..x31 hold when it starts (x4's is the frame's, ignored)."""

    regs: tuple[int, ...]
    program: Program


def relabelled(program: Program, block: int) -> Program:
    """`program` with each label `.L<name>` renamed `.Lb<block>_<name>`, and nothing else changed.

    The renaming is injective across blocks: after `.Lb` come the block's digits, then `_`.
    """

    def renamed(label: Label) -> Label:
        return Label(f".Lb{block}_{label.name[2:]}")

    def item(each: Item) -> Item:
        match each:
            case Label():
                return renamed(each)
            case Branch() | Jal():
                return replace(each, target=renamed(each.target))
            case _:
                return each

    return tuple(item(each) for each in program)


def lines(*text: str) -> str:
    """Each of `text` as one tab-indented line."""
    return "".join(f"\t{line}\n" for line in text)


def uart_bytes(label: str, reg: str) -> str:
    """Send the 8 bytes of `reg` to the UART (address in x5), least significant first."""
    return (
        lines("addi\tx8, x0, 8")
        + f"{label}:\n"
        + lines(
            f"sb\t{reg}, 0(x5)",
            f"srli\t{reg}, {reg}, 8",
            "addi\tx8, x8, -1",
            f"bne\tx8, x0, {label}b",
        )
    )


FRAME_REGS = tuple(r for r in range(1, SLOTS + 1) if r != 4)


def framed_block(index: int, block: Block) -> str:
    """Block `index` between its prologue (load from its record) and epilogue (save, report)."""
    return (
        lines(f"lla\tx4, .Lrec{index}")
        + lines(*(f"ld\tx{r}, {8 * (r - 1)}(x4)" for r in FRAME_REGS))
        + f"block{index}:\n"
        + print_program(relabelled(block.program, index))
        + lines(*(f"sd\tx{r}, {SAVE + 8 * (r - 1)}(x4)" for r in range(1, SLOTS + 1)))
        + lines(
            f"lui\tx5, {UART >> 12}",
            f"addi\tx6, x0, {ord('R')}",
            "sb\tx6, 0(x5)",
            f"addi\tx7, x4, {SAVE}",
            f"addi\tx8, x4, {RESUME}",
        )
        + "1:\n"
        + lines("lbu\tx6, 0(x7)", "sb\tx6, 0(x5)", "addi\tx7, x7, 1", "bne\tx7, x8, 1b")
        + f".Lresume{index}:\n"
    )


FINISH = (
    lines(
        f"lui\tx5, {TEST_DEVICE >> 12}",
        f"lui\tx6, {EXIT_0 >> 12}",
        f"addi\tx6, x6, {EXIT_0 & 0xFFF}",
        "sw\tx6, 0(x5)",
    )
    + SPIN
)

HANDLER = (
    "\t.p2align\t2\n.Ltrap:\n"
    + lines(f"lui\tx5, {UART >> 12}", f"addi\tx6, x0, {ord('T')}", "sb\tx6, 0(x5)")
    + lines("csrr\tx7, mcause")
    + uart_bytes("2", "x7")
    + lines("csrr\tx7, mepc")
    + uart_bytes("3", "x7")
    + lines(f"ld\tx7, {RESUME}(x4)", "csrw\tmepc, x7", "mret")
)


def record(index: int, block: Block) -> str:
    """Block `index`'s record: its initial values, the save area, the resume address."""
    return f".Lrec{index}:\n" + lines(
        *(f".dword\t{value}" for value in block.regs), f".zero\t{SAVE}", f".dword\t.Lresume{index}"
    )


def batch(blocks: Sequence[Block]) -> str:
    """The whole source that runs `blocks` in order in one boot and reports on each."""
    return (
        HEAD
        + lines("lla\tx5, .Ltrap", "csrw\tmtvec, x5")
        + "".join(framed_block(index, block) for index, block in enumerate(blocks))
        + FINISH
        + HANDLER
        + "\t.data\n\t.p2align\t3\n"
        + "".join(record(index, block) for index, block in enumerate(blocks))
    )


@dataclass(frozen=True, slots=True)
class Regs:
    """A block ran to its end: x1..x31 as it left them (x4's slot is the record's address)."""

    values: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Trap:
    """A block trapped: the exception `cause` and the address `mepc` of the instruction."""

    cause: int
    mepc: int


type Report = Regs | Trap


class DecodeError(Exception):
    """The UART's bytes are not a sequence of whole reports."""


def decode(uart: bytes) -> tuple[Report, ...]:
    """One report per `R` or `T` the frame wrote; any other byte, or a short one, is an error."""
    reports: list[Report] = []
    at = 0
    while at < len(uart):
        tag, size = uart[at : at + 1], {b"R": SAVE, b"T": 16}.get(uart[at : at + 1], 0)
        body = uart[at + 1 : at + 1 + size]
        if not size or len(body) != size:
            raise DecodeError(f"no whole report at byte {at} of {uart!r}")
        values = struct.unpack(f"<{size // 8}Q", body)
        reports.append(Regs(values) if tag == b"R" else Trap(*values))
        at += 1 + size
    return tuple(reports)
