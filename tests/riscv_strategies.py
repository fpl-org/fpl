"""Not a test: Hypothesis strategies over `fpl.asm.riscv` values, valid half.

Every value drawn here is in range by construction: 12-bit signed immediates and offsets, 6-bit
shift amounts (5-bit for the W forms), the unsigned 20-bit upper immediate, label names in the
checker's form `.L[A-Za-z0-9_]+`. Each range's two ends are drawn on purpose, not left to
chance. The deliberately invalid strategies belong to the checker's laws.
"""

from collections import defaultdict
from dataclasses import replace

from hypothesis import strategies as st

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


def shift(op: OpShift) -> st.SearchStrategy[Shift]:
    """`op` with an amount of 5 bits for the W forms, 6 bits otherwise."""
    return st.builds(Shift, st.just(op), regs, regs, between(0, 31 if op.endswith("w") else 63))


FORMS: dict[type[Instr], st.SearchStrategy[Instr]] = {
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


def instructions(*forms: type[Instr]) -> st.SearchStrategy[Instr]:
    """One valid instruction of one of `forms`, every class when none is named."""
    return st.one_of(*(FORMS[form] for form in forms or CLASSES))


# The forms that fall through to the next instruction and touch no memory.
STRAIGHT: tuple[type[Instr], ...] = (R, I, Shift, Upper, Fence)


@st.composite
def forward_branching(draw: st.DrawFn, n: int) -> Program:
    """One to `n` instructions, straight-line or `Branch`/`Jal`, each jump to a later label.

    The jump at instruction index i targets its own label `.L<i>`, defined before a drawn
    instruction index in `(i, count]` (`count` puts it after the last instruction), so labels
    are unique in the block and every run moves forward and falls off the end.
    """
    body = draw(st.lists(instructions(*STRAIGHT, Branch, Jal), min_size=1, max_size=n))
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
