"""Hypothesis strategies for A64 programs: the valid half (design section 6).

Valid means llvm-mc 21.1.8 assembles the printed text and llvm-objdump prints it back: each
slot draws only the registers it admits (sp or the zero register where the page allows it),
immediates inside their ranges with the boundaries included, and the constraints llvm-mc
enforces on loads, stores and pairs (no writeback base among the transfer registers, no load
pair into one register). No checker stands behind these draws yet; the text laws' llvm-mc
runs are what show them valid. Registers never include x18 and x29 (hole harness-registers);
sp only in the text strategies (`instructions()`), never in `straight_line` (sp-unobserved).
"""

from collections import defaultdict
from collections.abc import Callable
from functools import cache, partial

from hypothesis import find
from hypothesis import strategies as st

from fpl.asm.aarch64.alias import BITMASKS, ROWS, fired
from fpl.asm.aarch64.model import (
    AddSubCarry,
    AddSubExtended,
    AddSubImm,
    AddSubShifted,
    Adr,
    Bitfield,
    Branch,
    BranchCond,
    BranchReg,
    CompareBranch,
    Cond,
    CondCompareImm,
    CondCompareReg,
    CondSelect,
    DataProc1,
    DataProc2,
    Extend,
    Extract,
    Instr,
    Item,
    Label,
    LoadStore,
    LoadStoreUnscaled,
    LogicalImm,
    LogicalShifted,
    Mode,
    MoveWide,
    MulAdd,
    MulHigh,
    MulLong,
    Nop,
    Offset,
    OpAddSub,
    OpAddSubCarry,
    OpBitfield,
    OpBranch,
    OpBranchReg,
    OpCompareBranch,
    OpCondCompare,
    OpCondSelect,
    OpDataProc1,
    OpDataProc2,
    OpLoadStore,
    OpLoadStoreUnscaled,
    OpLogical,
    OpLogicalImm,
    OpMoveWide,
    OpMulAdd,
    OpMulHigh,
    OpMulLong,
    OpPair,
    OpTestBranch,
    Pair,
    PostIndex,
    PreIndex,
    Program,
    Reg,
    RegOffset,
    Shift,
    TestBranch,
    Width,
)

GENERAL = [reg for reg in Reg if reg not in (Reg.X18, Reg.X29, Reg.SP, Reg.ZR)]
widths = st.sampled_from(Width)
conds = st.sampled_from(Cond)
FLAGS = (OpAddSub.ADDS, OpAddSub.SUBS)


def regs(role: str = "gp") -> st.SearchStrategy[Reg]:
    """Registers for a slot: `gp` the general ones, `zr` also the zero register, `sp` also
    sp; the extra register is drawn half the time, so every alias on it is reached."""
    extra = {"zr": Reg.ZR, "sp": Reg.SP}.get(role)
    general = st.sampled_from(GENERAL)
    return general if extra is None else st.one_of(st.just(extra), general)


def bitmask_imms(width: Width) -> st.SearchStrategy[int]:
    """Logical immediates: the values DecodeBitMasks yields from some (N, immr, imms)."""
    return st.sampled_from(sorted(BITMASKS[width]))


def below(width: Width) -> st.SearchStrategy[int]:
    """[0, width), the alias boundaries (0, 7, 15, 31, width - 1) drawn often."""
    edges = st.sampled_from([0, 7, 15, width // 2 - 1, width - 1])
    return st.one_of(edges, st.integers(0, width - 1))


def either(reg: Reg, role: str) -> st.SearchStrategy[Reg]:
    """`reg` again half the time (Rn == Rm aliases), else a register for `role`."""
    return st.one_of(st.just(reg), regs(role))


@st.composite
def add_sub_imm(draw: st.DrawFn, sp: str) -> AddSubImm:
    """ADD, ADDS, SUB, SUBS (immediate): rd sp or zr by op, rn sp; imm in [0, 4095]."""
    op = draw(st.sampled_from(OpAddSub))
    rd = draw(regs("zr" if op in FLAGS else sp))
    imm = draw(st.one_of(st.just(0), st.integers(0, 4095)))
    return AddSubImm(op, draw(widths), rd, draw(regs(sp)), imm, draw(st.booleans()))


@st.composite
def add_sub_shifted(draw: st.DrawFn) -> AddSubShifted:
    """ADD, ADDS, SUB, SUBS (shifted register): lsl, lsr or asr below the width."""
    op, width = draw(st.sampled_from(OpAddSub)), draw(widths)
    rd, rn, rm = draw(regs("zr")), draw(regs("zr")), draw(regs("zr"))
    shift = draw(st.sampled_from([Shift.LSL, Shift.LSR, Shift.ASR]))
    return AddSubShifted(op, width, rd, rn, rm, shift, draw(below(width)))


@st.composite
def add_sub_extended(draw: st.DrawFn, sp: str) -> AddSubExtended:
    """ADD, ADDS, SUB, SUBS (extended register): rd sp or zr by op, rn sp; amount in [0, 4]."""
    op = draw(st.sampled_from(OpAddSub))
    rd, rn = draw(regs("zr" if op in FLAGS else sp)), draw(regs(sp))
    extend, amount = draw(st.sampled_from(Extend)), draw(st.integers(0, 4))
    return AddSubExtended(op, draw(widths), rd, rn, draw(regs("zr")), extend, amount)


@st.composite
def logical_imm(draw: st.DrawFn) -> LogicalImm:
    """AND, ORR, EOR, ANDS (immediate): an encodable value; rd zr only for ANDS."""
    op, width = draw(st.sampled_from(OpLogicalImm)), draw(widths)
    rd = draw(regs("zr" if op is OpLogicalImm.ANDS else "gp"))
    return LogicalImm(op, width, rd, draw(regs("zr")), draw(bitmask_imms(width)))


@st.composite
def logical(draw: st.DrawFn) -> LogicalShifted:
    """The logical (shifted register) operations: any shift below the width."""
    op, width = draw(st.sampled_from(OpLogical)), draw(widths)
    rd, rn, rm = draw(regs("zr")), draw(regs("zr")), draw(regs("zr"))
    return LogicalShifted(op, width, rd, rn, rm, draw(st.sampled_from(Shift)), draw(below(width)))


@st.composite
def move_wide(draw: st.DrawFn) -> MoveWide:
    """MOVN, MOVZ, MOVK: imm16 in [0, 65535] (0 and 65535 often), hw below width / 16."""
    op, width = draw(st.sampled_from(OpMoveWide)), draw(widths)
    imm16 = draw(st.one_of(st.sampled_from([0, 0xFFFF]), st.integers(0, 0xFFFF)))
    return MoveWide(op, width, draw(regs("zr")), imm16, draw(st.integers(0, width // 16 - 1)))


@st.composite
def bitfield(draw: st.DrawFn) -> Bitfield:
    """SBFM, BFM, UBFM: immr and imms below the width, the alias boundaries often, and immr
    0 (the extends) or imms + 1 (LSL) half the time, so every row is found."""
    op, width = draw(st.sampled_from(OpBitfield)), draw(widths)
    rd, rn = draw(regs("zr")), draw(regs("zr"))
    imms = draw(below(width))
    immr = draw(st.one_of(below(width), st.sampled_from([0, (imms + 1) % width])))
    return Bitfield(op, width, rd, rn, immr, imms)


@st.composite
def extract(draw: st.DrawFn) -> Extract:
    """EXTR: lsb below the width, rn == rm (ROR) half the time."""
    width, rd, rn = draw(widths), draw(regs("zr")), draw(regs("zr"))
    return Extract(width, rd, rn, draw(either(rn, "zr")), draw(below(width)))


@st.composite
def data_proc1(draw: st.DrawFn) -> DataProc1:
    """The one-source operations; REV32 at 64 bits only."""
    op = draw(st.sampled_from(OpDataProc1))
    width = Width.W64 if op is OpDataProc1.REV32 else draw(widths)
    return DataProc1(op, width, draw(regs("zr")), draw(regs("zr")))


@st.composite
def cond_select(draw: st.DrawFn) -> CondSelect:
    """The conditional selects; rn == rm half the time (CINC, CINV, CNEG, CSET, CSETM)."""
    op, width = draw(st.sampled_from(OpCondSelect)), draw(widths)
    rd, rn = draw(regs("zr")), draw(regs("zr"))
    return CondSelect(op, width, rd, rn, draw(either(rn, "zr")), draw(conds))


def three(make: Callable[..., Instr], ops: st.SearchStrategy[object]) -> st.SearchStrategy[Instr]:
    """An instruction of an op, a width and three registers that admit zr."""
    return st.builds(make, ops, widths, regs("zr"), regs("zr"), regs("zr"))


@st.composite
def load_store(draw: st.DrawFn) -> LoadStore:
    """A single-register load or store: unsigned offset (scaled, below 4096 units), pre- or
    post-index (simm9, the base not rt), or register offset (uxtw, lsl, sxtw, sxtx)."""
    op, rt, rn = draw(st.sampled_from(OpLoadStore)), draw(regs("zr")), draw(regs("sp"))
    kind = draw(st.sampled_from(["offset", "pre", "post", "register"]))
    if kind == "offset":
        return LoadStore(op, rt, Offset(rn, op.size * draw(st.integers(0, 4095))))
    if kind == "register":
        option = draw(st.sampled_from([Extend.UXTW, Extend.UXTX, Extend.SXTW, Extend.SXTX]))
        return LoadStore(op, rt, RegOffset(rn, draw(regs("zr")), option, draw(st.booleans())))
    base = draw(regs("sp").filter(lambda reg: reg is not rt))
    index = PreIndex if kind == "pre" else PostIndex
    return LoadStore(op, rt, index(base, draw(st.integers(-256, 255))))


@st.composite
def pair(draw: st.DrawFn) -> Pair:
    """STP, LDP, LDPSW (64-bit only): imm a multiple of the access size in [-64, 63] of
    them; loads never into one register twice, writeback never on a transfer register."""
    op, mode = draw(st.sampled_from(OpPair)), draw(st.sampled_from(Mode))
    width = Width.W64 if op is OpPair.LDPSW else draw(widths)
    rt = draw(regs("zr"))
    rt2 = draw(regs("zr").filter(lambda reg: op is OpPair.STP or reg is not rt))
    rn = draw(regs("sp").filter(lambda reg: mode is Mode.OFFSET or reg not in (rt, rt2)))
    size = 4 if op is OpPair.LDPSW else width // 8
    return Pair(op, width, rt, rt2, rn, size * draw(st.integers(-64, 63)), mode)


def register_only(sp: str) -> dict[type, st.SearchStrategy[Instr]]:
    """The register-only classes, by class; `sp` is the role of the slots that admit sp."""
    zr = regs("zr")
    return {
        AddSubImm: add_sub_imm(sp),
        AddSubShifted: add_sub_shifted(),
        AddSubExtended: add_sub_extended(sp),
        AddSubCarry: three(AddSubCarry, st.sampled_from(OpAddSubCarry)),
        LogicalImm: logical_imm(),
        LogicalShifted: logical(),
        MoveWide: move_wide(),
        Bitfield: bitfield(),
        Extract: extract(),
        DataProc2: three(DataProc2, st.sampled_from(OpDataProc2)),
        DataProc1: data_proc1(),
        MulAdd: st.builds(MulAdd, st.sampled_from(OpMulAdd), widths, zr, zr, zr, zr),
        MulLong: st.builds(MulLong, st.sampled_from(OpMulLong), zr, zr, zr, zr),
        MulHigh: st.builds(MulHigh, st.sampled_from(OpMulHigh), zr, zr, zr),
        CondSelect: cond_select(),
        CondCompareReg: st.builds(
            CondCompareReg,
            st.sampled_from(OpCondCompare),
            widths,
            zr,
            zr,
            st.integers(0, 15),
            conds,
        ),
        CondCompareImm: st.builds(
            CondCompareImm,
            st.sampled_from(OpCondCompare),
            widths,
            zr,
            st.integers(0, 31),
            st.integers(0, 15),
            conds,
        ),
    }


# Every label-free class, by class, for the text laws: sp where a slot admits it.
BY_CLASS: dict[type, st.SearchStrategy[Instr]] = register_only("sp") | {
    Nop: st.just(Nop()),
    BranchReg: st.builds(BranchReg, st.sampled_from(OpBranchReg), regs()),
    LoadStore: load_store(),
    LoadStoreUnscaled: st.builds(
        LoadStoreUnscaled,
        st.sampled_from(OpLoadStoreUnscaled),
        regs("zr"),
        regs("sp"),
        st.integers(-256, 255),
    ),
    Pair: pair(),
}


def instructions() -> st.SearchStrategy[Instr]:
    """One label-free instruction of any class, its operands in range."""
    return st.one_of(*BY_CLASS.values())


def straight_line(n: int = 16) -> st.SearchStrategy[list[Instr]]:
    """Up to `n` register-only instructions, flags included; never sp."""
    return st.lists(st.one_of(*register_only("gp").values()), max_size=n)


@st.composite
def control(draw: st.DrawFn, label: Label) -> list[Instr]:
    """A forward transfer to `label`: b, bl, b.cond, cbz/cbnz, tbz/tbnz, or the atomic pair
    `adr xk, label` then `br`, `blr` or `ret` on xk."""
    kind = draw(st.sampled_from(["b", "b.cond", "cbz", "tbz", "adr"]))
    if kind == "b":
        return [Branch(draw(st.sampled_from(OpBranch)), label)]
    if kind == "b.cond":
        return [BranchCond(draw(conds), label)]
    if kind == "cbz":
        op = draw(st.sampled_from(OpCompareBranch))
        return [CompareBranch(op, draw(widths), draw(regs("zr")), label)]
    if kind == "tbz":
        op = draw(st.sampled_from(OpTestBranch))
        return [TestBranch(op, draw(regs("zr")), draw(st.integers(0, 63)), label)]
    reg = draw(regs())
    return [Adr(reg, label), BranchReg(draw(st.sampled_from(OpBranchReg)), reg)]


@st.composite
def forward_branching(draw: st.DrawFn, n: int = 12) -> Program:
    """Straight-line code with transfers to labels defined later; a label may follow the
    last instruction. Labels precede the transfers inserted at their position, so the `adr`
    pair stays adjacent and nothing lands between its halves."""
    body = draw(straight_line(n))
    positions = draw(st.sets(st.integers(1, len(body)), max_size=3)) if body else set[int]()
    labels = {at: Label(f".L{k}") for k, at in enumerate(sorted(positions))}
    jumps: defaultdict[int, list[Instr]] = defaultdict(list)
    for at, label in labels.items():
        for _ in range(draw(st.integers(1, 2))):
            jumps[draw(st.integers(0, at - 1))] += draw(control(label))
    items: list[Item] = []
    for at in range(len(body) + 1):
        items += [labels[at]] if at in labels else []
        items += jumps[at] + body[at : at + 1]
    return tuple(items)


def programs() -> st.SearchStrategy[Program]:
    """Valid programs: label-free instructions, or forward-branching code with labels."""
    return st.one_of(st.lists(instructions(), max_size=24).map(tuple), forward_branching())


def fires(row: object, instr: Instr) -> bool:
    """Whether `row` is the alias `instr` prints as."""
    return fired(instr) is row


@cache
def witnesses() -> Program:
    """One drawn instruction per alias row, from its class's strategy: every row is reached."""
    return tuple(
        find(BY_CLASS[cls], partial(fires, row)) for cls, rows in ROWS.items() for row in rows
    )


def unaliased(instr: Instr) -> bool:
    """Whether `instr` prints in its base form."""
    return fired(instr) is None


@cache
def bases() -> Program:
    """One drawn instruction per class in its base form: every base reading is reached.
    Bitfield has none in range: every in-range SBFM, BFM and UBFM prints as an alias."""
    drawn = (strategy for cls, strategy in BY_CLASS.items() if cls is not Bitfield)
    return tuple(find(strategy, unaliased) for strategy in drawn)
