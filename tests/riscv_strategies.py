"""Not a test: Hypothesis strategies over `fpl.asm.riscv` values, valid and deliberately invalid.

The valid half is in range by construction: 12-bit signed immediates and offsets, 6-bit
shift amounts (5-bit for the W forms), the unsigned 20-bit upper immediate, label names in the
checker's form `.L[A-Za-z0-9_]+`. Each range's two ends are drawn on purpose, not left to
chance.

The invalid half serves the checker's laws: `invalid_programs()` puts one to three violations
into a valid program and says which problems they are; `far_jumps()` puts a jump just inside
or just past its reach.
"""

from collections import defaultdict
from dataclasses import dataclass, replace

from hypothesis import strategies as st
from riscv_virt import WINDOW, Block

from fpl.asm.riscv.check import Kind
from fpl.asm.riscv.eval import size
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
    OpBare,
    OpBranch,
    OpI,
    OpLoad,
    OpR,
    OpShift,
    OpStore,
    OpUpper,
    Program,
    R,
    Reg,
    Shift,
    Store,
    Upper,
)


def between(low: int, high: int) -> st.SearchStrategy[int]:
    """An integer in `[low, high]`, either end drawn on purpose."""
    return st.one_of(st.sampled_from((low, high)), st.integers(low, high))


regs = st.sampled_from(Reg)
imm12 = between(-2048, 2047)
labels = st.from_regex(r"\.L[A-Za-z0-9_]+", fullmatch=True).map(Label)


# One strategy per instruction class.
type Table = dict[type[Instr], st.SearchStrategy[Instr]]


def forms(regs: st.SearchStrategy[Reg]) -> Table:
    """One strategy per class, every register operand drawn from `regs`.

    A shift amount has 5 bits for the W forms, 6 bits otherwise.
    """

    def shift(op: OpShift) -> st.SearchStrategy[Shift]:
        high = 31 if op.endswith("w") else 63
        return st.builds(Shift, st.just(op), regs, regs, between(0, high))

    return {
        R: st.builds(R, st.sampled_from(OpR), regs, regs, regs),
        I: st.builds(I, st.sampled_from(OpI), regs, regs, imm12),
        Shift: st.sampled_from(OpShift).flatmap(shift),
        Upper: st.builds(Upper, st.sampled_from(OpUpper), regs, between(0, (1 << 20) - 1)),
        Load: st.builds(Load, st.sampled_from(OpLoad), regs, regs, imm12),
        Store: st.builds(Store, st.sampled_from(OpStore), regs, regs, imm12),
        Branch: st.builds(Branch, st.sampled_from(OpBranch), regs, regs, labels),
        Jal: st.builds(Jal, regs, labels),
        Jalr: st.builds(Jalr, regs, regs, imm12),
        Fence: st.builds(
            Fence, st.builds(Access, st.integers(0, 15)), st.builds(Access, st.integers(0, 15))
        ),
        Bare: st.builds(Bare, st.sampled_from(OpBare)),
    }


FORMS = forms(regs)
# The registers a block run in the QEMU virt frame may name: not x3 (the window, unit 6) and
# not x4 (the frame's record), neither read nor written (hole `harness-registers`).
FRAME_REGS = st.sampled_from(tuple(reg for reg in Reg if reg not in {Reg.X3, Reg.X4}))
FRAME_FORMS = forms(FRAME_REGS)


def instructions(*classes: type[Instr], table: Table = FORMS) -> st.SearchStrategy[Instr]:
    """One valid instruction of one of `classes` from `table`, every class when none is named."""
    return st.one_of(*(table[form] for form in classes or CLASSES))


# The forms that fall through to the next instruction and touch no memory.
STRAIGHT: tuple[type[Instr], ...] = (R, I, Shift, Upper, Fence)


def straight_line(n: int, table: Table = FORMS) -> st.SearchStrategy[Program]:
    """One to `n` instructions of the `STRAIGHT` forms, drawn from `table`."""
    return st.lists(instructions(*STRAIGHT, table=table), min_size=1, max_size=n).map(tuple)


def in_window(access: Load | Store) -> st.SearchStrategy[Load | Store]:
    """`access` from x3 at an offset that keeps all its bytes in the window, aligned or not."""
    return between(0, WINDOW - size(access)).map(lambda offset: replace(access, offset=offset))


# A load or store of a frame register through x3, the window's address.
ACCESSES = st.one_of(
    st.builds(Load, st.sampled_from(OpLoad), FRAME_REGS, st.just(Reg.X3), st.just(0)),
    st.builds(Store, st.sampled_from(OpStore), FRAME_REGS, st.just(Reg.X3), st.just(0)),
).flatmap(in_window)


def memory_code(n: int) -> st.SearchStrategy[Program]:
    """One to `n` instructions, straight-line in the frame's registers or `ACCESSES`."""
    body = st.one_of(instructions(*STRAIGHT, table=FRAME_FORMS), ACCESSES)
    return st.lists(body, min_size=1, max_size=n).map(tuple)


@st.composite
def forward_branching(draw: st.DrawFn, n: int, table: Table = FORMS) -> Program:
    """One to `n` instructions, straight-line or `Branch`/`Jal`, each jump to a later label.

    The jump at instruction index i targets its own label `.L<i>`, defined before a drawn
    instruction index in `(i, count]` (`count` puts it after the last instruction), so labels
    are unique in the block and every run moves forward and falls off the end.
    """
    body = draw(st.lists(instructions(*STRAIGHT, Branch, Jal, table=table), min_size=1, max_size=n))
    defined: defaultdict[int, list[Item]] = defaultdict(list)
    for index, instr in enumerate(body):
        if isinstance(instr, Branch | Jal):
            jump = replace(instr, target=Label(f".L{index}"))
            body[index] = jump
            defined[draw(st.integers(index + 1, len(body)))].append(jump.target)
    return tuple(
        item
        for index in range(len(body) + 1)
        for item in (*defined[index], *body[index : index + 1])
    )


NOP = I(OpI.ADDI, Reg.X0, Reg.X0, 0)
FAR = Label(".Lfar")


def padded(jump: Branch | Jal, offset: int) -> Program:
    """`jump` to `.Lfar`, defined `offset` bytes away (a multiple of 4), the gap filled by nops.

    Forward, the label follows `offset / 4 - 1` nops after the jump; backward (or at 0), it
    precedes `-offset / 4` nops before the jump. The offset is exactly the checker's
    `4 x (instruction index of the label - instruction index of the jump)`.
    """
    jump = replace(jump, target=FAR)
    if offset > 0:
        return (jump, *(NOP,) * (offset // 4 - 1), FAR)
    return (FAR, *(NOP,) * (-offset // 4), jump)


def beyond(low: int, high: int) -> st.SearchStrategy[int]:
    """An integer just past either end of `[low, high]`, or far past it."""
    past = st.one_of(st.just(0), st.integers(1, 16), st.integers(17, 1 << 64))
    return st.one_of(past.map(lambda d: high + 1 + d), past.map(lambda d: low - 1 - d))


def bad_shift(op: OpShift) -> st.SearchStrategy[tuple[Instr, Kind]]:
    """`op` with an amount past its 5 or 6 bits, and the kind the checker calls it."""
    kind, high = (Kind.SHAMT5, 31) if op.endswith("w") else (Kind.SHAMT6, 63)
    return st.tuples(st.builds(Shift, st.just(op), regs, regs, beyond(0, high)), st.just(kind))


imm12_beyond = beyond(-2048, 2047)
# An instruction with its one ranged operand out of range, and the kind of its problem.
OUT_OF_RANGE: st.SearchStrategy[tuple[Instr, Kind]] = st.one_of(
    st.tuples(st.builds(I, st.sampled_from(OpI), regs, regs, imm12_beyond), st.just(Kind.IMM12)),
    st.tuples(
        st.builds(Load, st.sampled_from(OpLoad), regs, regs, imm12_beyond), st.just(Kind.IMM12)
    ),
    st.tuples(
        st.builds(Store, st.sampled_from(OpStore), regs, regs, imm12_beyond), st.just(Kind.IMM12)
    ),
    st.tuples(st.builds(Jalr, regs, regs, imm12_beyond), st.just(Kind.IMM12)),
    st.sampled_from(OpShift).flatmap(bad_shift),
    st.tuples(
        st.builds(Upper, st.sampled_from(OpUpper), regs, beyond(0, (1 << 20) - 1)),
        st.just(Kind.IMM20),
    ),
)


@dataclass(frozen=True, slots=True)
class Invalid:
    """A program with violations put in, and the `(index, kind)` of each problem they are."""

    program: Program
    problems: frozenset[tuple[int | None, Kind]]


@st.composite
def invalid_programs(draw: st.DrawFn, n: int = 20) -> Invalid:
    """A `forward_branching(n)` program with one to three violations inserted at drawn places.

    A violation is an operand out of range (`OUT_OF_RANGE`), a second definition of a label
    (both definitions inserted, the later one the problem), or a jump to a label never defined
    (a whole-program problem). The k-th violation's labels are `.Ldup<k>` and `.Lnowhere<k>`,
    which the base's `.L<digits>` never are, so the base's labels stay unique and defined and
    the problems are exactly the ones inserted. Inserting a few items moves no jump out of reach.
    """
    entries: list[tuple[Item, Kind | None]] = [(item, None) for item in draw(forward_branching(n))]
    problems: set[tuple[int | None, Kind]] = set()

    def insert(item: Item, kind: Kind | None, at_least: int = 0) -> int:
        at = draw(st.integers(at_least, len(entries)))
        entries.insert(at, (item, kind))
        return at

    for k in range(draw(st.integers(1, 3))):
        match draw(st.sampled_from(("range", "duplicate", "undefined"))):
            case "range":
                insert(*draw(OUT_OF_RANGE))
            case "duplicate":
                label = Label(f".Ldup{k}")
                insert(label, Kind.DUPLICATE_LABEL, insert(label, None) + 1)
            case _:
                jump = draw(JUMPS[Branch] | JUMPS[Jal])
                insert(replace(jump, target=Label(f".Lnowhere{k}")), None)
                problems.add((None, Kind.UNDEFINED_LABEL))
    problems |= {(index, kind) for index, (_, kind) in enumerate(entries) if kind is not None}
    return Invalid(tuple(item for item, _ in entries), frozenset(problems))


# Jumps to `.Lfar`, by class.
JUMPS: dict[type[Branch | Jal], st.SearchStrategy[Branch | Jal]] = {
    Branch: st.builds(Branch, st.sampled_from(OpBranch), regs, regs, st.just(FAR)),
    Jal: st.builds(Jal, regs, st.just(FAR)),
}


BRANCH_REACH = (4092, 4096, -4096, -4100)
JAL_REACH = (1048572, 1048576, -1048576, -1048580)
# Nine branch cases to one jal case: a far jal is 262,144 items long.
REACH: tuple[tuple[type[Branch | Jal], int], ...] = (
    *((Branch, offset) for offset in BRANCH_REACH * 9),
    *((Jal, offset) for offset in JAL_REACH),
)


def far_jumps() -> st.SearchStrategy[Program]:
    """A branch or jal just inside or just past its reach, forward or backward: `padded`.

    Offsets are multiples of 4 (every instruction is 4 bytes), so the edges drawn are the last
    reachable offset and the first unreachable one on each side.
    """
    return st.sampled_from(REACH).flatmap(
        lambda reach: JUMPS[reach[0]].map(lambda jump: padded(jump, reach[1]))
    )


# The register values the spec's edges are made of, drawn on purpose besides uniform ones.
EDGES = (0, 1, 2, (1 << 64) - 1, 1 << 63, (1 << 63) - 1, 1 << 31, (1 << 31) - 1, (1 << 32) - 1)
u64s = st.one_of(st.sampled_from((*EDGES, 0xFFFF_FFFF_8000_0000)), between(0, (1 << 64) - 1))


def blocks(k: int, programs: st.SearchStrategy[Program]) -> st.SearchStrategy[list[Block]]:
    """One to `k` blocks for one boot, each a program of `programs`, 31 values for x1..x31 and
    the window's bytes."""
    values = st.lists(u64s, min_size=31, max_size=31).map(tuple)
    window = st.binary(min_size=WINDOW, max_size=WINDOW)
    return st.lists(st.builds(Block, values, window, programs), min_size=1, max_size=k)
