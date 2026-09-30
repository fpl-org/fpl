"""Hypothesis strategies for A64 programs: the valid half and the invalid half (design
section 6).

Valid means llvm-mc 21.1.8 assembles the printed text and llvm-objdump prints it back: each
slot draws only the registers it admits (sp or the zero register where the page allows it),
immediates inside their ranges with the boundaries included, and the constraints llvm-mc
enforces on loads, stores and pairs (no writeback base among the transfer registers, no load
pair into one register); `check` finds nothing in them (strategies-split), and the text laws'
llvm-mc runs show them valid. Registers never include x18 and x29 (hole harness-registers);
sp only in the text strategies (`instructions()`), never in `straight_line` (sp-unobserved).

The invalid half, `invalid_programs()` and `far_branches()`, draws a `Drawn`: a program, the
`Kind` of violation it carries, and the items that carry it. One kind per program, since
llvm-mc reports its fixup and undefined-symbol errors only for a program that parsed: an
out-of-range branch next to a line error would show on one side only. Replacements take the
place of instructions, never of labels, so no definition goes missing by accident. The
exclusions the agreement laws make (`rewritten`, `checker_only`, `misnamed`) are predicates
over the program, so the laws and the draws read the same sets.
"""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import cache, partial

from aarch64_frame import MIDDLE, OBSERVED, Block
from hypothesis import find
from hypothesis import strategies as st

from fpl.asm.aarch64.alias import BITMASKS, ROWS, fired
from fpl.asm.aarch64.check import NAME, Kind
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

TOP = (1 << 64) - 1
EDGES = [0, 1, 0x7FFF_FFFF, 0x8000_0000, 0xFFFF_FFFF, 1 << 32, (1 << 63) - 1, 1 << 63, TOP]
GENERAL = [reg for reg in Reg if reg not in (Reg.X18, Reg.X29, Reg.SP, Reg.ZR)]
OPTIONS = [Extend.UXTW, Extend.UXTX, Extend.SXTW, Extend.SXTX]  # a register offset's
widths = st.sampled_from(Width)
conds = st.sampled_from(Cond)
FLAGS = (OpAddSub.ADDS, OpAddSub.SUBS)


def regs(role: str = "gp") -> st.SearchStrategy[Reg]:
    """Registers for a slot: `gp` the general ones, `zr` also the zero register, `sp` also
    sp; the extra register is drawn half the time, so every alias on it is reached."""
    extra = {"zr": Reg.ZR, "sp": Reg.SP}.get(role)
    general = st.sampled_from(GENERAL)
    return general if extra is None else st.one_of(st.just(extra), general)


def u64s() -> st.SearchStrategy[int]:
    """Register values in [0, 2**64), the sign and width edges drawn often."""
    return st.one_of(st.sampled_from(EDGES), st.integers(0, TOP))


def nzcvs() -> st.SearchStrategy[int]:
    """NZCV as four bits, all 16."""
    return st.integers(0, 15)


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
        option = draw(st.sampled_from(OPTIONS))
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


@st.composite
def block(draw: st.DrawFn) -> Block:
    """A block for a run: the 29 observed registers and NZCV drawn, x18 and x29 zero (the
    frame leaves them to the platform, and no block reads them), a straight_line or
    forward_branching program."""
    drawn = dict(zip(OBSERVED, draw(st.lists(u64s(), min_size=29, max_size=29)), strict=True))
    regs = tuple(drawn.get(reg, 0) for reg in range(31))
    program = draw(st.one_of(straight_line().map(tuple), forward_branching()))
    return Block(regs, draw(nzcvs()), program)


def blocks(k: int = 8) -> st.SearchStrategy[list[Block]]:
    """A batch of one to `k` blocks for one run."""
    return st.lists(block(), min_size=1, max_size=k)


WINDOW = 256
LAST = WINDOW - 16  # the x27 cursor stays at or below it, so any access at it fits
UNBASED = [reg for reg in GENERAL if reg not in (Reg.X27, Reg.X28)]


@dataclass(frozen=True, slots=True)
class Room:
    """What a memory access may use: transfer registers, the index register (holding
    [0, 31]) and x27's offset into the window, in [0, LAST]."""

    rts: st.SearchStrategy[Reg]
    index: Reg
    cursor: int


type Access = tuple[Instr, int]  # an access and x27's offset after it


@st.composite
def moved(draw: st.DrawFn, cursor: int, size: int) -> int:
    """A new x27 offset in [0, LAST], a multiple of `size` away from `cursor`."""
    return cursor + size * draw(st.integers(-(cursor // size), (LAST - cursor) // size))


@st.composite
def offset_access(draw: st.DrawFn, room: Room) -> Access:
    """An unsigned (scaled) offset from x28, or from x27 at its cursor."""
    op, from27 = draw(st.sampled_from(OpLoadStore)), draw(st.booleans())
    start = room.cursor if from27 else 0
    units = draw(st.integers(0, (WINDOW - op.size - start) // op.size))
    base = Reg.X27 if from27 else Reg.X28
    return LoadStore(op, draw(room.rts), Offset(base, op.size * units)), room.cursor


@st.composite
def register_access(draw: st.DrawFn, room: Room) -> Access:
    """x28 plus the index register by any option, scaled or not: at most 31 * 8 bytes in."""
    op, option = draw(st.sampled_from(OpLoadStore)), draw(st.sampled_from(OPTIONS))
    addr = RegOffset(Reg.X28, room.index, option, draw(st.booleans()))
    return LoadStore(op, draw(room.rts), addr), room.cursor


@st.composite
def indexed_access(draw: st.DrawFn, room: Room) -> Access:
    """A pre- or post-index access through x27, which moves to a new offset in [0, LAST]."""
    op, pre = draw(st.sampled_from(OpLoadStore)), draw(st.booleans())
    after = draw(moved(room.cursor, 1))
    addr = (
        PreIndex(Reg.X27, after - room.cursor) if pre else PostIndex(Reg.X27, after - room.cursor)
    )
    return LoadStore(op, draw(room.rts), addr), after


@st.composite
def unscaled_access(draw: st.DrawFn, room: Room) -> Access:
    """LDUR or STUR from x28 or x27 at any byte offset that fits: the misaligned accesses."""
    op, from27 = draw(st.sampled_from(OpLoadStoreUnscaled)), draw(st.booleans())
    start = room.cursor if from27 else 0
    simm9 = draw(st.integers(-start, WINDOW - op.size - start))
    base = Reg.X27 if from27 else Reg.X28
    return LoadStoreUnscaled(op, draw(room.rts), base, simm9), room.cursor


@st.composite
def pair_access(draw: st.DrawFn, room: Room) -> Access:
    """STP, LDP or LDPSW: at an offset from x28 or x27, or pre- or post-indexed through x27;
    a load never into one register twice."""
    op, mode = draw(st.sampled_from(OpPair)), draw(st.sampled_from(Mode))
    width = Width.W64 if op is OpPair.LDPSW else draw(widths)
    size = 4 if op is OpPair.LDPSW else width // 8
    rt = draw(room.rts)
    rt2 = draw(room.rts.filter(lambda reg: op is OpPair.STP or reg is not rt))
    if mode is not Mode.OFFSET:
        after = draw(moved(room.cursor, size))
        return Pair(op, width, rt, rt2, Reg.X27, after - room.cursor, mode), after
    from27 = draw(st.booleans())
    start = room.cursor if from27 else 0
    units = draw(st.integers(-(start // size), (WINDOW - 2 * size - start) // size))
    base = Reg.X27 if from27 else Reg.X28
    return Pair(op, width, rt, rt2, base, size * units, mode), room.cursor


ACCESSES = [offset_access, register_access, indexed_access, unscaled_access, pair_access]


@st.composite
def memory_code(draw: st.DrawFn, index: Reg, n: int = 12) -> list[Instr]:
    """Up to `n` loads, stores and pairs inside the 256-byte window at x28: x28 is never
    written, x27 starts at window + 128 and is the only writeback base, `index` holds [0, 31]
    and is the only register offset; aligned or not. Transfer registers are neither of them
    nor `index` (hole harness-registers), the zero register included."""
    rts = st.sampled_from([*(reg for reg in UNBASED if reg is not index), Reg.ZR])
    cursor, code = MIDDLE, list[Instr]()
    for _ in range(draw(st.integers(0, n))):
        kind = draw(st.sampled_from(ACCESSES))
        instr, cursor = draw(kind(Room(rts, index, cursor)))
        code.append(instr)
    return code


@st.composite
def memory_block(draw: st.DrawFn) -> Block:
    """A block with a window: 256 drawn bytes, the observed registers drawn but x27 and x28
    zero (the frame points them at the window) and the index register in [0, 31]."""
    index = draw(st.sampled_from(UNBASED))
    drawn = dict(zip(OBSERVED, draw(st.lists(u64s(), min_size=29, max_size=29)), strict=True))
    drawn |= {Reg.X27: 0, Reg.X28: 0, index: draw(st.integers(0, 31))}
    regs = tuple(drawn.get(reg, 0) for reg in range(31))
    window = draw(st.binary(min_size=WINDOW, max_size=WINDOW))
    return Block(regs, draw(nzcvs()), tuple(draw(memory_code(index))), window)


def memory_blocks(k: int = 8) -> st.SearchStrategy[list[Block]]:
    """A batch of one to `k` memory blocks for one run."""
    return st.lists(memory_block(), min_size=1, max_size=k)


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


# The invalid half.


@dataclass(frozen=True, slots=True)
class Drawn:
    """A program, the kind of violation drawn into it (None: none), and the items replaced."""

    program: Program
    kind: Kind | None
    replaced: tuple[int, ...]


def rewrites_imm(imm: int) -> bool:
    """AddSubImm values llvm-mc silently rewrites (design section 4): 4096 k with 1 <= k <=
    4095 (`#k, lsl #12`), [-4095, -1] (the opposite op), -4096 k (both)."""
    k, rest = divmod(abs(imm), 4096)
    return -4095 <= imm <= -1 or (imm != 0 and rest == 0 and 1 <= k <= 4095)


def rewrites_offset(imm: int, size: int) -> bool:
    """Unsigned offsets llvm-mc silently rewrites to the unscaled form: in [-256, 255] and
    negative or not a multiple of the access size."""
    return -256 <= imm <= 255 and (imm < 0 or imm % size != 0)


def rewritten(program: Program) -> bool:
    """Whether an item of `program` is in a silent-rewrite set."""
    return any(
        (isinstance(item, AddSubImm) and rewrites_imm(item.imm))
        or (
            isinstance(item, LoadStore)
            and isinstance(item.addr, Offset)
            and rewrites_offset(item.addr.imm, item.op.size)
        )
        for item in program
    )


def accepted_cell(i: Pair) -> bool:
    """Whether `i` is one of the five UNPREDICTABLE pair cells llvm-mc 21.1.8 accepts:
    rt == rt2 with ldp pre- or post-indexed or ldpsw pre-indexed; rt != rt2 with post-indexed
    ldpsw and rn == rt or rn == rt2 (rn not sp)."""
    twice = i.op is not OpPair.STP and i.rt is i.rt2
    base = i.mode is not Mode.OFFSET and i.rn in (i.rt, i.rt2) and i.rn is not Reg.SP
    ldp_twice = i.op is OpPair.LDP and i.mode is not Mode.OFFSET
    ldpsw_twice = i.op is OpPair.LDPSW and i.mode is Mode.PRE
    ldpsw_base = i.op is OpPair.LDPSW and i.mode is Mode.POST
    return (twice and not base and (ldp_twice or ldpsw_twice)) or (
        base and not twice and ldpsw_base
    )


def checker_only(program: Program) -> bool:
    """Whether an item of `program` is a checker-only cell."""
    return any(isinstance(item, Pair) and accepted_cell(item) for item in program)


def misnamed(program: Program) -> bool:
    """Whether a label of `program`, defined or referenced, is not `.L`-local: llvm-mc takes
    any symbol, so LABEL_NAME is not an oracle case."""
    names = (item if isinstance(item, Label) else getattr(item, "target", None) for item in program)
    return any(isinstance(n, Label) and NAME.fullmatch(n.name) is None for n in names)


def outside(low: int, high: int, edges: list[int]) -> st.SearchStrategy[int]:
    """Integers in [low, high], the named edges often."""
    return st.one_of(st.sampled_from(edges), st.integers(low, high))


@st.composite
def bad_imm12(draw: st.DrawFn) -> AddSubImm:
    """IMM12: the silent-rewrite sets and the values both sides refuse, lsl12 clear (llvm-mc
    also rewrites `#-1, lsl #12`)."""
    silent = st.one_of(
        st.integers(1, 4095).map(lambda k: 4096 * k),
        st.integers(-4095, -1),
        st.integers(1, 4095).map(lambda k: -4096 * k),
    )
    loud = st.one_of(
        outside(4096, 1 << 26, [4097, 16777215]), outside(-(1 << 26), -4096, [-4097])
    ).filter(lambda imm: not rewrites_imm(imm))
    imm = draw(st.one_of(silent, loud))
    return replace(draw(add_sub_imm("sp")), imm=imm, lsl12=False)


@st.composite
def bad_bitmask(draw: st.DrawFn) -> LogicalImm:
    """BITMASK: a value at the width that DecodeBitMasks never yields (0 and all ones too)."""
    i = draw(logical_imm())
    top = (1 << i.width) - 1
    imm = draw(outside(0, top, [0, top]).filter(lambda v: v not in BITMASKS[i.width]))
    return replace(i, imm=imm)


@st.composite
def bad_shift(draw: st.DrawFn) -> Instr:
    """SHIFT_AMOUNT: an amount at or past the width, or ror in add and sub."""
    i = draw(st.one_of(add_sub_shifted(), logical()))
    if isinstance(i, AddSubShifted) and draw(st.booleans()):
        return replace(i, shift=Shift.ROR, amount=draw(st.integers(1, i.width - 1)))
    return replace(i, amount=draw(st.integers(i.width, 63 + i.width // 32)))


@st.composite
def bad_move_wide(draw: st.DrawFn) -> MoveWide:
    """MOVE_WIDE: imm16 past 65535, or hw at or past width / 16."""
    i = draw(move_wide())
    if draw(st.booleans()):
        return replace(i, imm16=draw(outside(1 << 16, 1 << 20, [1 << 16])))
    return replace(i, hw=draw(st.integers(i.width // 16, 4)))


@st.composite
def bad_bitfield(draw: st.DrawFn) -> Instr:
    """BITFIELD: immr, imms or lsb at or past the width."""
    i = draw(st.one_of(bitfield(), extract()))
    past = draw(st.integers(i.width, 63 + i.width // 32))
    if isinstance(i, Extract):
        return replace(i, lsb=past)
    return replace(i, immr=past) if draw(st.booleans()) else replace(i, imms=past)


@st.composite
def bad_cond_imm(draw: st.DrawFn) -> Instr:
    """COND_IMM: imm5 past 31 or nzcv past 15."""
    i = draw(st.one_of(register_only("gp")[CondCompareImm], register_only("gp")[CondCompareReg]))
    assert isinstance(i, CondCompareImm | CondCompareReg)
    if isinstance(i, CondCompareImm) and draw(st.booleans()):
        return replace(i, imm5=draw(st.integers(32, 63)))
    return replace(i, nzcv=draw(st.integers(16, 31)))


@st.composite
def bad_offset(draw: st.DrawFn) -> Instr:
    """OFFSET: unsigned offsets in the silent sets and outside them (misaligned past 255,
    past 4095 units, below -256), pre- and post-index and unscaled offsets past a simm9,
    and pair offsets misaligned or past an imm7."""
    kind = draw(st.sampled_from(["offset", "index", "unscaled", "pair"]))
    simm9 = st.one_of(st.integers(256, 600), st.integers(-600, -257))
    if kind == "unscaled":
        unscaled = draw(BY_CLASS[LoadStoreUnscaled])
        assert isinstance(unscaled, LoadStoreUnscaled)
        return replace(unscaled, simm9=draw(simm9))
    if kind == "pair":
        misfit = st.integers(-1100, 1100).filter(lambda v: v % 4 or abs(v) > 504)
        return replace(draw(pair()), imm=draw(misfit))
    i = draw(load_store().filter(lambda i: not isinstance(i.addr, RegOffset)))
    if kind == "index" and isinstance(i.addr, PreIndex | PostIndex):
        return replace(i, addr=replace(i.addr, imm=draw(simm9)))
    size, rn = i.op.size, i.addr.rn
    far = st.one_of(
        st.integers(256, 4095 * size).filter(lambda v: v % size != 0),
        outside(4096 * size, 4200 * size, [4096 * size]),
        st.integers(-600, -257),
        st.integers(-256, 255).filter(partial(rewrites_offset, size=size)),
    )
    return LoadStore(i.op, i.rt, Offset(rn, draw(far)))


@st.composite
def bad_reg31(draw: st.DrawFn) -> Instr:
    """REG31: sp in a slot of the zero register, or the zero register in a slot of sp, in
    slots where llvm-mc refuses it (it takes `add sp, x2, x3` as the extended form)."""
    sp, zr, gp = st.just(Reg.SP), regs("zr"), regs()
    choices: list[st.SearchStrategy[Instr]] = [
        add_sub_imm("sp").map(lambda i: replace(i, rn=Reg.ZR)),
        st.builds(AddSubCarry, st.sampled_from(OpAddSubCarry), widths, sp, zr, zr),
        st.builds(DataProc2, st.sampled_from(OpDataProc2), widths, zr, zr, sp),
        st.builds(MulAdd, st.sampled_from(OpMulAdd), widths, gp, sp, zr, zr),
        cond_select().map(lambda i: replace(i, rd=Reg.SP)),
        pair().map(lambda i: replace(i, rt=Reg.SP)),
        load_store().map(lambda i: replace(i, rt=Reg.SP)),
    ]
    return draw(st.one_of(choices))


@st.composite
def bad_width(draw: st.DrawFn) -> Instr:
    """WIDTH: rev32 or ldpsw at 32 bits."""
    if draw(st.booleans()):
        return DataProc1(OpDataProc1.REV32, Width.W32, draw(regs("zr")), draw(regs("zr")))
    i = draw(pair().filter(lambda i: i.op is OpPair.LDPSW))
    return replace(i, width=Width.W32)


@st.composite
def pair_cell(draw: st.DrawFn, op: OpPair, width: Width, mode: Mode, overlap: str) -> Pair:
    """A pair in one cell of section 4's grids: `overlap` "rt2" puts rt2 = rt (loads), "rn=rt"
    or "rn=rt2" puts the writeback base on that transfer register (rt != rt2)."""
    rt = draw(regs())
    if overlap == "rt2":
        rn = draw(regs("sp").filter(lambda r: r is not rt))
        return Pair(op, width, rt, rt, rn, 0, mode)
    rt2 = draw(regs().filter(lambda r: r is not rt))
    return Pair(op, width, rt, rt2, rt if overlap == "rn=rt" else rt2, 0, mode)


# Section 4's two grids: rt == rt2 for the loads in every mode; the base on a transfer register
# for every pair with writeback. X and W for ldp and stp, X for ldpsw.
PAIRS = [(OpPair.LDP, Width.W64), (OpPair.LDP, Width.W32), (OpPair.LDPSW, Width.W64)]
CELLS = [(op, width, mode, "rt2") for op, width in PAIRS for mode in Mode] + [
    (op, width, mode, overlap)
    for op, width in [*PAIRS[:2], (OpPair.STP, Width.W64), (OpPair.STP, Width.W32), PAIRS[2]]
    for mode in (Mode.PRE, Mode.POST)
    for overlap in ("rn=rt", "rn=rt2")
]


@st.composite
def bad_unpredictable(draw: st.DrawFn) -> Instr:
    """UNPREDICTABLE: a single load or store writing back onto rt, or a pair in any cell."""
    if draw(st.booleans()):
        i = draw(load_store().filter(lambda i: isinstance(i.addr, PreIndex | PostIndex)))
        rt = draw(regs())
        return replace(i, rt=rt, addr=replace(i.addr, rn=rt))
    return draw(pair_cell(*draw(st.sampled_from(CELLS))))


UNDEFINED = Label(".Lnowhere")
VIOLATIONS: dict[Kind, st.SearchStrategy[Item]] = {
    Kind.IMM12: bad_imm12(),
    Kind.BITMASK: bad_bitmask(),
    Kind.SHIFT_AMOUNT: bad_shift(),
    Kind.EXTEND_AMOUNT: add_sub_extended("sp").flatmap(
        lambda i: st.integers(5, 8).map(lambda amount: replace(i, amount=amount))
    ),
    Kind.MOVE_WIDE: bad_move_wide(),
    Kind.BITFIELD: bad_bitfield(),
    Kind.COND_IMM: bad_cond_imm(),
    Kind.OFFSET: bad_offset(),
    Kind.REG31: bad_reg31(),
    Kind.WIDTH: bad_width(),
    Kind.UNPREDICTABLE: bad_unpredictable(),
    Kind.DUPLICATE_LABEL: st.just(Label(".Ldup")),
    Kind.UNDEFINED_LABEL: st.one_of(
        st.builds(Branch, st.sampled_from(OpBranch), st.just(UNDEFINED)),
        st.builds(BranchCond, conds, st.just(UNDEFINED)),
        st.builds(Adr, regs(), st.just(UNDEFINED)),
    ),
    Kind.LABEL_NAME: st.sampled_from(["L1", "bad", ".L", ".Lx-y"]).map(Label),
}


@st.composite
def invalid_programs(draw: st.DrawFn) -> Drawn:
    """A valid program with one to three of its instructions replaced by violations of one
    drawn kind; for DUPLICATE_LABEL a first `.Ldup` definition leads the program."""
    kind = draw(st.sampled_from(list(VIOLATIONS)))
    base = draw(programs().filter(lambda p: any(not isinstance(i, Label) for i in p)))
    items = [Label(".Ldup"), *base] if kind is Kind.DUPLICATE_LABEL else list(base)
    spots = [at for at, item in enumerate(items) if not isinstance(item, Label)]
    replaced = sorted(draw(st.sets(st.sampled_from(spots), min_size=1, max_size=3)))
    for at in replaced:
        items[at] = draw(VIOLATIONS[kind])
    return Drawn(tuple(items), kind, tuple(replaced))


# Branch reach, as the checker's: k for an offset in [-2^k, 2^k - 4] bytes.
FAR = {TestBranch: 15, BranchCond: 20, CompareBranch: 20, Adr: 20}


@st.composite
def far_branches(draw: st.DrawFn) -> Drawn:
    """A branch or adr padded with nops to offset 2^k - 8, 2^k - 4, 2^k or 2^k + 4 bytes,
    forward or back (tbz k = 15; b.cond, cbz and adr k = 20, drawn one time in sixteen:
    262,145 items). Only the nops and the one transfer, so the fixup error is llvm-mc's only."""
    near = draw(st.integers(0, 15)) != 0
    cls = TestBranch if near else draw(st.sampled_from([BranchCond, CompareBranch, Adr]))
    far = draw(st.sampled_from([-8, -4, 0, 4])) + (1 << FAR[cls])
    label = Label(".Lfar")
    make: dict[type, Callable[[], Instr]] = {
        TestBranch: lambda: TestBranch(OpTestBranch.TBZ, Reg.X1, 3, label),
        BranchCond: lambda: BranchCond(Cond.EQ, label),
        CompareBranch: lambda: CompareBranch(OpCompareBranch.CBZ, Width.W64, Reg.X2, label),
        Adr: lambda: Adr(Reg.X1, label),
    }
    branch, nops = make[cls](), (Nop(),) * (far // 4)
    if draw(st.booleans()):  # forward: the label follows far // 4 - 1 nops after the branch
        program: Program = (branch, *nops[1:], label)
        reach, at = far <= (1 << FAR[cls]) - 4, 0
    else:  # back: the label leads, far // 4 nops, then the branch at -far
        program = (label, *nops, branch)
        reach, at = far <= 1 << FAR[cls], len(program) - 1
    return Drawn(program, None if reach else Kind.BRANCH_RANGE, () if reach else (at,))


def excluded(program: Program) -> bool:
    """Whether the agreement laws leave `program` out: a silent rewrite, a checker-only cell,
    or a label name llvm-mc takes as any symbol."""
    return rewritten(program) or checker_only(program) or misnamed(program)
