"""Oracle: the tools come from the pin, the printed text is what llvm-objdump prints, and the
checker refuses what llvm-mc and ld.lld refuse."""

import re
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st
from riscv_oracle import (
    NAMES,
    VERSIONS,
    ToolchainError,
    Translation,
    assemble,
    disassemble,
    link,
    listing,
    parse_paths,
    resolve,
    toolchain,
    translate,
)
from riscv_strategies import (
    FAR,
    JAL_REACH,
    NOP,
    Invalid,
    far_jumps,
    forward_branching,
    instructions,
    invalid_programs,
    padded,
)
from riscv_virt import HEAD

from fpl.asm.riscv.check import Kind, check
from fpl.asm.riscv.model import (
    Bare,
    Branch,
    Fence,
    I,
    Instr,
    Jal,
    Jalr,
    Label,
    Load,
    OpBranch,
    OpI,
    OpShift,
    OpUpper,
    Program,
    R,
    Reg,
    Shift,
    Store,
    Upper,
)
from fpl.asm.riscv.text import print_program

GOOD = [f"/nix/store/0000-tool/bin/{name}" for name in NAMES]
# Lines a resolution may print that are not the answer: the shell hook's banner, a tool found
# outside the store, blank lines, and the right paths out of place.
NOISE = [
    *GOOD,
    "==> wiring the git hooks",
    f"/usr/bin/{NAMES[0]}",
    "",
    "/nix/store/x/bin/cc",
]


def assert_refused(lines: list[str], stderr: str) -> None:
    """`lines` on stdout are not the answer: the error shows them and what was said on stderr."""
    stdout = "".join(f"{line}\n" for line in lines)
    done = subprocess.CompletedProcess(["bash"], 0, stdout, stderr)
    with pytest.raises(ToolchainError) as error:
        parse_paths("cmd", done)
    assert stdout in str(error.value)
    assert stderr in str(error.value)


@given(
    st.sampled_from(NAMES),
    st.lists(st.one_of(st.sampled_from(NOISE), st.text(max_size=12)), max_size=6),
    st.text(max_size=12),
)
def test_each_tool_is_the_pinned_one_from_the_riscv_layer(
    name: str, lines: list[str], stderr: str
) -> None:
    """[law: tools-from-pin] One /nix/store path per tool at its pinned version, or an error.

    Resolved once per process from the worktree's own flake (`nix develop <root>#riscv`),
    so every call after the first is the same object; each tool is an absolute /nix/store
    path under its own name and reports its pinned version. Only stdout counts: the four
    paths, one line per tool in order, are the answer whatever stderr says. Any other stdout
    is a `ToolchainError` that shows stdout and stderr. A missing `nix` is a
    `ToolchainError` naming the command it tried, never a skip.
    """
    tools = toolchain()
    path = tools.by_name()[name]
    assert toolchain() is tools
    assert path.is_absolute()
    assert str(path).startswith("/nix/store/")
    assert path.name == name
    assert path.is_file()
    done = subprocess.run([path, "--version"], capture_output=True, text=True, check=True)
    assert f" {VERSIONS[name]}" in done.stdout

    answer = subprocess.CompletedProcess(["bash"], 0, "".join(f"{p}\n" for p in GOOD), stderr)
    assert parse_paths("cmd", answer).by_name()[name] == Path(GOOD[NAMES.index(name)])
    assume(lines != GOOD)
    assert_refused(lines, stderr)
    with pytest.raises(ToolchainError, match="/nonexistent/nix develop"):
        resolve(nix="/nonexistent/nix")


def test_one_store_path_per_tool_in_order_is_the_answer() -> None:
    done = subprocess.CompletedProcess(["bash"], 0, "".join(f"{line}\n" for line in GOOD), "")
    assert parse_paths("cmd", done).by_name() == {
        n: Path(p) for n, p in zip(NAMES, GOOD, strict=True)
    }


@pytest.mark.parametrize(
    "lines",
    [
        *([*GOOD[:i], f"/usr/bin/{name}", *GOOD[i + 1 :]] for i, name in enumerate(NAMES)),
        [*GOOD, GOOD[0]],
        GOOD[:-1],
        ["==> wiring the git hooks", *GOOD],
    ],
)
def test_a_path_off_the_store_a_line_too_many_or_too_few_or_a_banner_is_an_error(
    lines: list[str],
) -> None:
    assert_refused(lines, "said on stderr")


def fake_nix(folder: Path, banner_to: str) -> str:
    """A `nix` that prints the hook banner to `banner_to` (a shell redirection), then GOOD."""
    nix = folder / "nix"
    paths = " ".join(GOOD)
    nix.write_text(
        f"#!/bin/sh\necho '==> wiring the git hooks' {banner_to}\nprintf '%s\\n' {paths}\n"
    )
    nix.chmod(0o755)
    return str(nix)


def test_resolve_reads_the_paths_from_stdout_and_ignores_stderr(tmp_path: Path) -> None:
    tools = resolve(nix=fake_nix(tmp_path, ">&2"))
    assert tools.by_name() == {n: Path(p) for n, p in zip(NAMES, GOOD, strict=True)}


def test_resolve_refuses_a_banner_on_stdout_showing_it(tmp_path: Path) -> None:
    with pytest.raises(ToolchainError, match="==> wiring the git hooks"):
        resolve(nix=fake_nix(tmp_path, ""))


# Every form but the control transfers, whose operand objdump prints as a resolved address.
LABEL_FREE = (R, I, Shift, Upper, Load, Store, Jalr, Fence, Bare)


@given(st.lists(instructions(*LABEL_FREE), min_size=1, max_size=20).map(tuple))
def test_the_printed_text_is_the_disassembly(program: Program) -> None:
    """[law: print-is-disassembly] objdump prints the printer's lines back, as many of them.

    The printed program, after `_start` and nothing else, assembles and links; the lines
    llvm-objdump prints for it, address column removed, are the printer's lines, leading tab
    removed. The programs are the valid strategies' (in range by construction), standing in
    for "the checker accepts" until the checker exists.
    """
    tools = toolchain()
    text = print_program(program)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        assembled = assemble(tools, HEAD + text, work)
        assert assembled.returncode == 0, assembled.stderr
        linked = link(tools, work)
        assert linked.returncode == 0, linked.stderr
        lines = disassemble(tools, work)
    assert lines == [line[1:] for line in text.splitlines()]


def resolved(program: Program, base: int) -> list[str]:
    """The printed lines of `program`'s instructions, each target label replaced by its address.

    Every instruction is 4 bytes and a label takes none, so a label's address is `base` plus 4
    times the number of instructions before it. The address is spelled as objdump spells it.
    """
    address: dict[str, int] = {}
    count = 0
    for item in program:
        if isinstance(item, Label):
            address[item.name] = base + 4 * count
        else:
            count += 1
    lines: list[str] = []
    for item, text in zip(program, print_program(program).splitlines(), strict=True):
        match item:
            case Label():
                continue
            case Branch() | Jal():
                lines.append(
                    text[1:].removesuffix(item.target.name) + hex(address[item.target.name])
                )
            case _:
                lines.append(text[1:])
    return lines


@given(forward_branching(20))
def test_each_branch_and_jal_lands_on_its_label(program: Program) -> None:
    """[law: control-targets-agree] Branches and jals keep their operands and reach their labels.

    Each `Branch` and `Jal` of a labelled program, printed after `_start` and linked, is
    disassembled with the same mnemonic and registers, and with the absolute target
    `base + 4 x (instruction index of the label)`, `base` being the address objdump gives the
    first instruction. Every other line is the printed one, and there are as many lines.
    """
    tools = toolchain()
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        assembled = assemble(tools, HEAD + print_program(program), work)
        assert assembled.returncode == 0, assembled.stderr
        linked = link(tools, work)
        assert linked.returncode == 0, linked.stderr
        disassembly = listing(tools, work)
    base = disassembly[0][0]
    assert [text for _, text in disassembly] == resolved(program, base)


# An error llvm-mc attributes to a line of `prog.s`; `<unknown>:0` errors name no line.
ERROR = re.compile(r"prog\.s:(\d+):\d+: error:")
# The problems llvm-mc reports at the line of the item they are about.
LINE_KINDS = frozenset(
    {
        Kind.IMM12,
        Kind.SHAMT6,
        Kind.SHAMT5,
        Kind.IMM20,
        Kind.DUPLICATE_LABEL,
        Kind.JAL_RANGE,
    }
)
# Item i of a program printed after `HEAD` is line i + 1 + HEAD_LINES of the source.
HEAD_LINES = HEAD.count("\n")


@given(invalid_programs())
def test_llvm_mc_refuses_the_lines_the_checker_names(case: Invalid) -> None:
    """[law: checker-agrees-per-line] llvm-mc's error lines are the checker's problem lines.

    For each invalid program, printed after `_start`, the set of lines llvm-mc reports errors
    on equals the set of lines of the checker's line-attributable problems (`IMM12`, `SHAMT6`,
    `SHAMT5`, `IMM20`, `DUPLICATE_LABEL`, `JAL_RANGE`). An undefined label is a whole-program
    error in both (`<unknown>:0`), so it names no line on either side.
    """
    assert_lines_agree(case.program)


def assert_lines_agree(program: Program) -> Translation:
    """The lines llvm-mc refuses in `program`, printed after `_start`, are the checker's."""
    translation = translate(toolchain(), HEAD + print_program(program))
    refused = {int(n) - HEAD_LINES - 1 for n in ERROR.findall(translation.mc.stderr)}
    named = {problem.index for problem in check(program) if problem.kind in LINE_KINDS}
    assert refused == named, translation.mc.stderr
    return translation


def one(*instrs: Instr) -> list[Program]:
    """Each instruction as a program of its own."""
    return [(instr,) for instr in instrs]


# The last value in range and the first past it for each ranged operand, a second definition,
# and the four jal reaches: the edges the generators draw only now and then.
EDGES: list[Program] = [
    *one(*(I(OpI.ADDI, Reg.X1, Reg.X2, imm) for imm in (2047, 2048, -2048, -2049))),
    *one(*(Shift(OpShift.SLLI, Reg.X1, Reg.X2, n) for n in (63, 64, -1))),
    *one(*(Shift(OpShift.SLLIW, Reg.X1, Reg.X2, n) for n in (31, 32))),
    *one(*(Upper(OpUpper.LUI, Reg.X1, imm) for imm in ((1 << 20) - 1, 1 << 20, 0, -1))),
    (Label(".Ldup"), NOP, Label(".Ldup")),
    *(padded(Jal(Reg.X1, FAR), offset) for offset in JAL_REACH),
]


@pytest.mark.parametrize("program", EDGES)
def test_the_checker_and_llvm_mc_agree_at_each_edge(program: Program) -> None:
    """The regression at the edges, line by line and program by program: 2047 and 2048 for an
    imm12, 63 and 64 for a shamt6, 1048572 and 1048576 for a jal forward, and so on."""
    translation = assert_lines_agree(program)
    assert (check(program) == ()) == translation.accepted, translation


@given(
    st.one_of(
        forward_branching(20),
        invalid_programs().map(lambda case: case.program),
        st.lists(instructions(), max_size=20).map(tuple),
        far_jumps(),
    )
)
def test_the_checker_accepts_what_llvm_mc_and_ld_lld_accept(program: Program) -> None:
    """[law: checker-agrees-per-program] `check(p) == ()` iff llvm-mc and ld.lld both exit 0.

    Over valid programs, invalid ones, arbitrary instructions whose jumps name labels the
    program never defines, and jumps at the edge of their reach (a jal past it included);
    the program is printed after `_start`. A program with a
    `BRANCH_RANGE` problem is left out: llvm-mc relaxes that branch and accepts it, which
    no-silent-relaxation checks.
    """
    problems = check(program)
    assume(all(problem.kind is not Kind.BRANCH_RANGE for problem in problems))
    translation = translate(toolchain(), HEAD + print_program(program))
    assert (problems == ()) == translation.accepted, (problems, translation)


# The branch that is taken exactly when `op` is not.
INVERSE = {
    OpBranch.BEQ: OpBranch.BNE,
    OpBranch.BNE: OpBranch.BEQ,
    OpBranch.BLT: OpBranch.BGE,
    OpBranch.BGE: OpBranch.BLT,
    OpBranch.BLTU: OpBranch.BGEU,
    OpBranch.BGEU: OpBranch.BLTU,
}


def assert_relaxed_exactly_out_of_reach(program: Program) -> None:
    """The checker refuses the program's one branch exactly when llvm-mc silently relaxes it.

    llvm-mc and ld.lld accept the program either way. In reach, the checker says nothing and
    the disassembly is the printed program, targets resolved. Out of reach, the checker's one
    problem is `BRANCH_RANGE` at the branch, and the round trip finds the extra instruction:
    the branch inverted to skip the next instruction, then `jal x0` to the label.
    """
    at, branch = next((i, item) for i, item in enumerate(program) if isinstance(item, Branch))
    translation = translate(toolchain(), HEAD + print_program(program))
    assert translation.accepted, translation
    base = translation.listing[0][0]
    lines = [text for _, text in translation.listing]
    expected = resolved(program, base)
    problems = [(problem.index, problem.kind) for problem in check(program)]
    if not problems:
        assert lines == expected
        return
    assert problems == [(at, Kind.BRANCH_RANGE)]
    j = sum(not isinstance(item, Label) for item in program[:at])
    label = program.index(FAR)
    before = sum(not isinstance(item, Label) for item in program[:label])
    target = base + 4 * (before + (at < label))
    inverted = print_program((replace(branch, op=INVERSE[branch.op]),))[1:-1]
    skip = inverted.removesuffix(FAR.name) + hex(base + 4 * j + 8)
    assert lines == [*expected[:j], skip, f"jal\tx0, {hex(target)}", *expected[j + 1 :]]


@given(far_jumps())
def test_a_branch_out_of_reach_is_refused_by_the_checker_not_by_llvm_mc(
    program: Program,
) -> None:
    """[law: no-silent-relaxation] llvm-mc relaxes a far branch; the checker refuses it.

    For the branches of `far_jumps()`: past the reach (4096 forward, -4100 backward, the
    first offsets past [-4096, 4094] a program of 4-byte instructions can have) the checker
    reports `BRANCH_RANGE`, llvm-mc accepts, and the object holds one instruction more than
    the program, the extra one found by the round trip; at 4092 and -4096 (the last offsets
    in reach) neither the checker nor the round trip objects. Far jals are refused by
    llvm-mc itself, which checker-agrees-per-program checks.
    """
    assume(any(isinstance(item, Branch) for item in program))
    assert_relaxed_exactly_out_of_reach(program)


BEQ = Branch(OpBranch.BEQ, Reg.X1, Reg.X2, FAR)


@pytest.mark.parametrize("offset", [4092, 4096])
def test_a_beq_at_4092_is_kept_and_at_4096_is_relaxed(offset: int) -> None:
    """The regression at the forward edge: 4092 is the last offset in reach, 4096 the first past."""
    assert_relaxed_exactly_out_of_reach(padded(BEQ, offset))
