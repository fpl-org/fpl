"""The operand-form checker: what llvm-mc 21.1.8 refuses, said of the values before any text.

`check(program)` returns every problem it finds, in three passes over the items: ranged
operands, label definitions, then jumps. Each problem names the item it is about by its
position in the program, except `UNDEFINED_LABEL`, which is about the whole program (llvm-mc
reports it with no line: `<unknown>:0: error: Undefined temporary symbol`) and is reported once
per name. An empty tuple promises that llvm-mc and ld.lld accept the printed program.

The ranges are the ones llvm-mc prints in its errors. Every instruction is 4 bytes (no C
extension) and a label takes none, so a jump's offset is exactly `4 x (instruction index of
the label - instruction index of the jump)`, to the label's first definition.

`BRANCH_RANGE` is the one problem llvm-mc does not report: it rewrites an out-of-range branch
into an inverted branch over a `jal` and exits 0. The checker is what refuses that program.
Reserved registers are a convention of the test frame, not of the ISA, and are not checked.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import assert_never

from fpl.asm.riscv.model import (
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
    Shift,
    Store,
    Upper,
)


class Kind(StrEnum):
    """What is wrong: an operand out of its range, or a label ill-formed, doubled or missing."""

    IMM12 = "imm12"  # I.imm and the Load, Store and Jalr offsets
    SHAMT6 = "shamt6"  # slli, srli, srai
    SHAMT5 = "shamt5"  # slliw, srliw, sraiw
    IMM20 = "imm20"  # lui, auipc: the unsigned 20-bit field
    DUPLICATE_LABEL = "duplicate-label"  # every definition after the first
    UNDEFINED_LABEL = "undefined-label"  # a name referenced and never defined
    LABEL_NAME = "label-name"  # a name outside `.L[A-Za-z0-9_]+`
    JAL_RANGE = "jal-range"  # a jal's offset
    BRANCH_RANGE = "branch-range"  # a branch's offset


@dataclass(frozen=True, slots=True)
class Problem:
    """One thing llvm-mc would refuse: where (an item's position, `None` for the whole program)."""

    index: int | None
    kind: Kind
    detail: str


# Each ranged kind's inclusive range of values.
RANGES: dict[Kind, tuple[int, int]] = {
    Kind.IMM12: (-2048, 2047),
    Kind.SHAMT6: (0, 63),
    Kind.SHAMT5: (0, 31),
    Kind.IMM20: (0, (1 << 20) - 1),
    Kind.JAL_RANGE: (-(1 << 20), (1 << 20) - 2),
    Kind.BRANCH_RANGE: (-(1 << 12), (1 << 12) - 2),
}
NAME = re.compile(r"\.L[A-Za-z0-9_]+")


def ranged(instr: Instr) -> tuple[Kind, int] | None:
    """The one ranged operand of `instr` with its kind; `None` for the forms without one."""
    match instr:
        case I():
            return Kind.IMM12, instr.imm
        case Load() | Store() | Jalr():
            return Kind.IMM12, instr.offset
        case Shift():
            return (Kind.SHAMT5 if instr.op.endswith("w") else Kind.SHAMT6), instr.shamt
        case Upper():
            return Kind.IMM20, instr.imm
        case R() | Branch() | Jal() | Fence() | Bare():
            return None
        case _:
            assert_never(instr)


def outside(index: int, kind: Kind, value: int, what: str) -> Iterator[Problem]:
    """A problem of `kind` at `index` when `value` leaves the kind's range."""
    low, high = RANGES[kind]
    if not low <= value <= high:
        yield Problem(index, kind, f"{what} {value} is outside [{low}, {high}]")


def misnamed(index: int, name: str) -> Iterator[Problem]:
    """A `LABEL_NAME` problem at `index` when `name` is not `.L[A-Za-z0-9_]+`."""
    if not NAME.fullmatch(name):
        yield Problem(index, Kind.LABEL_NAME, f"label {name!r} is not .L[A-Za-z0-9_]+")


def numbered(program: Program) -> Iterator[tuple[int, int, Item]]:
    """Each item with its position and its instruction index: the instructions before it."""
    count = 0
    for index, item in enumerate(program):
        yield index, count, item
        if not isinstance(item, Label):
            count += 1


def operands(program: Program) -> Iterator[Problem]:
    """The immediates, offsets and shift amounts out of range."""
    for index, item in enumerate(program):
        if not isinstance(item, Label) and (operand := ranged(item)) is not None:
            yield from outside(index, *operand, item.op)


def targets(program: Program) -> dict[str, int]:
    """Each defined name's instruction index, at its first definition."""
    first: dict[str, int] = {}
    for _, count, item in numbered(program):
        if isinstance(item, Label):
            first.setdefault(item.name, count)
    return first


def definitions(program: Program) -> Iterator[Problem]:
    """The ill-named definitions and every definition of a name after its first."""
    seen: set[str] = set()
    for index, item in enumerate(program):
        if isinstance(item, Label):
            yield from misnamed(index, item.name)
            if item.name in seen:
                yield Problem(index, Kind.DUPLICATE_LABEL, f"{item.name} is already defined")
            seen.add(item.name)


def jumps(program: Program) -> Iterator[Problem]:
    """The ill-named targets and the jumps out of reach, then each undefined name once."""
    first = targets(program)
    undefined: dict[str, None] = {}
    for index, count, item in numbered(program):
        if isinstance(item, Branch | Jal):
            name = item.target.name
            yield from misnamed(index, name)
            if name not in first:
                undefined[name] = None
                continue
            kind = Kind.BRANCH_RANGE if isinstance(item, Branch) else Kind.JAL_RANGE
            yield from outside(index, kind, 4 * (first[name] - count), f"{item.op} to {name}:")
    for name in undefined:
        yield Problem(None, Kind.UNDEFINED_LABEL, f"{name} is referenced but never defined")


def check(program: Program) -> tuple[Problem, ...]:
    """Every problem of `program`: operands, then definitions, then jumps; `()` when none."""
    return (*operands(program), *definitions(program), *jumps(program))
