"""Oracle tests against the pinned LLVM tools: first, that they are the pinned ones."""

import platform
import subprocess
from dataclasses import replace
from functools import cache, partial
from pathlib import Path

import pytest
from aarch64_oracle import (
    LLVM,
    NAMES,
    QEMU,
    SDK,
    ToolchainError,
    Tools,
    command,
    disassemble,
    parse_paths,
    reported,
    resolve,
    toolchain,
    verdict,
)
from aarch64_strategies import (
    Drawn,
    add_sub_imm,
    excluded,
    far_branches,
    instructions,
    invalid_programs,
    load_store,
    programs,
    rewrites_offset,
    witnesses,
)
from hypothesis import example, given, settings
from hypothesis import strategies as st

from fpl.asm.aarch64.check import Kind, check
from fpl.asm.aarch64.model import (
    AddSubImm,
    Instr,
    LoadStore,
    Offset,
    OpAddSub,
    OpLoadStore,
    Program,
    Reg,
    Width,
)
from fpl.asm.aarch64.text import print_program

DARWIN = (
    'nix develop "$(git rev-parse --show-toplevel)#aarch64" -c bash -c '
    '\'command -v llvm-mc llvm-objdump ld64.lld; printf "%s\\n" "$SDKROOT"\''
)
LINUX = (
    'nix develop "$(git rev-parse --show-toplevel)#aarch64" -c bash -c '
    "'command -v llvm-mc llvm-objdump ld.lld qemu-aarch64'"
)
# What scripts/setup prints to stdout when the shell hook runs it on a first entry.
setup_lines = st.from_regex(r"==> [ -~]*", fullmatch=True)


@cache
def versions(tools: Tools) -> tuple[str, str]:
    """llvm-mc's version report, and qemu-aarch64's (Linux) or the SDK's settings (Darwin)."""
    if tools.system == "Linux":
        return reported(tools.mc), reported(tools.host)
    return reported(tools.mc), (tools.host / "SDKSettings.json").read_text()


def said(stdout: str) -> subprocess.CompletedProcess[str]:
    """A finished `nix develop` that printed `stdout`."""
    return subprocess.CompletedProcess(["bash"], 0, stdout, "")


@given(noise=st.lists(st.tuples(st.integers(0, 4), setup_lines)))
def test_toolchain_from_pin(
    tmp_path_factory: pytest.TempPathFactory, worker_id: str, noise: list[tuple[int, str]]
) -> None:
    """[law: tools-from-pin] toolchain(), once per session, returns this platform's four items
    as /nix/store paths from the worktree's flake, in order by basename, at the pinned
    versions; its line filter keeps the same four paths among any interleaved `==>` lines."""
    tools = toolchain(tmp_path_factory, worker_id)
    system = platform.system()
    assert tools.system == system
    assert command(system) == {"Darwin": DARWIN, "Linux": LINUX}[system]
    assert tuple(path.name for path in tools.paths()) == NAMES[system]
    assert all(path.is_absolute() and str(path).startswith("/nix/store/") for path in tools.paths())
    assert all(path.exists() for path in tools.paths())
    mc, host = versions(tools)
    assert f"version {LLVM}" in mc
    assert f"version {QEMU}" in host if system == "Linux" else f'"Version":"{SDK}"' in host
    lines = [str(path) for path in tools.paths()]
    for at, line in sorted(noise, reverse=True):
        lines.insert(at, line)
    assert parse_paths(system, "nix develop", said("\n".join(lines) + "\n")) == tools.paths()


def darwin(*names: str) -> str:
    """Darwin's stdout with `names` as the basenames of its /nix/store lines."""
    return "".join(f"/nix/store/0-x/bin/{name}\n" for name in names)


@pytest.mark.parametrize(
    "stdout",
    [
        darwin("llvm-mc", "llvm-objdump", "MacOSX.sdk"),
        darwin("llvm-mc", "ld64.lld", "llvm-objdump", "MacOSX.sdk"),
        darwin("llvm-mc", "llvm-objdump", "ld64.lld", "MacOSX.sdk", "ld.lld"),
        darwin("llvm-mc", "llvm-objdump", "ld.lld", "qemu-aarch64"),
    ],
    ids=["a-missing-tool", "a-tool-out-of-order", "one-too-many", "the-linux-set"],
)
def test_the_filter_refuses_anything_but_the_four_in_order_showing_the_output(
    stdout: str,
) -> None:
    with pytest.raises(ToolchainError, match="expected one /nix/store/ path each") as refused:
        parse_paths("Darwin", "nix develop", said("==> setting up\n" + stdout))
    assert stdout in str(refused.value)


def test_the_filter_drops_setup_lines_between_the_tools() -> None:
    stdout = "==> a\n" + darwin("llvm-mc", "llvm-objdump") + "==> b\n" + darwin("ld64.lld")
    stdout += "==> c\n/nix/store/0-sdk/MacOSX.sdk\n==> d\n"
    names = [path.name for path in parse_paths("Darwin", "nix develop", said(stdout))]
    assert names == list(NAMES["Darwin"])


def test_another_platform_is_an_error_not_a_skip() -> None:
    with pytest.raises(ToolchainError, match="no aarch64 route for platform 'Windows'"):
        command("Windows")


def test_no_nix_is_an_error_showing_the_command(tmp_path: Path) -> None:
    missing = str(tmp_path / "nix")
    with pytest.raises(ToolchainError, match="expected one /nix/store/") as refused:
        resolve(platform.system(), nix=missing)
    assert f"{missing} develop" in str(refused.value)


@settings(backend="hypothesis")
@given(program=st.lists(instructions(), min_size=1, max_size=48).map(tuple))
def test_printed_text_is_what_llvm_objdump_prints(
    tmp_path_factory: pytest.TempPathFactory, worker_id: str, program: Program
) -> None:
    """[law: print-is-disassembly] For label-free programs the valid strategies draw, llvm-mc
    exits 0, and the lines llvm-objdump prints for the object, normalised, equal the lines of
    print_program(p), as many of them."""
    tools = toolchain(tmp_path_factory, worker_id)
    text = print_program(program)
    assert disassemble(tools, text, tmp_path_factory.mktemp("text")) == text.splitlines()


def test_every_alias_row_prints_as_llvm_objdump_prints_it(
    tmp_path_factory: pytest.TempPathFactory, worker_id: str
) -> None:
    """Every alias row, reached by the strategies, prints what llvm-objdump prints."""
    tools = toolchain(tmp_path_factory, worker_id)
    text = print_program(witnesses())
    assert disassemble(tools, text, tmp_path_factory.mktemp("rows")) == text.splitlines()


agreeable = st.one_of(invalid_programs(), far_branches()).filter(
    lambda drawn: not excluded(drawn.program)
)


@settings(backend="hypothesis")
@given(drawn=agreeable)
def test_the_checker_and_llvm_mc_refuse_the_same_lines(
    tmp_path_factory: pytest.TempPathFactory, worker_id: str, drawn: Drawn
) -> None:
    """[law: checker-agrees-per-line] For invalid programs without the silent-rewrite sets and
    the five checker-only cells (out-of-range values outside the sets stay in), the lines
    llvm-mc reports errors on are the printed lines of the checker's line problems."""
    tools = toolchain(tmp_path_factory, worker_id)
    found = verdict(tools, print_program(drawn.program), tmp_path_factory.mktemp("lines"))
    lines = {p.index + 1 for p in check(drawn.program) if p.index is not None}
    assert found.lines == lines, found.said


@settings(backend="hypothesis")
@given(drawn=st.one_of(programs().map(lambda p: Drawn(p, None, ())), agreeable))
def test_the_checker_accepts_exactly_what_llvm_mc_assembles(
    tmp_path_factory: pytest.TempPathFactory, worker_id: str, drawn: Drawn
) -> None:
    """[law: checker-agrees-per-program] For valid and invalid programs without the
    silent-rewrite sets or the checker-only cells, check(p) == () iff llvm-mc -filetype=obj
    exits 0 (no linker)."""
    tools = toolchain(tmp_path_factory, worker_id)
    found = verdict(tools, print_program(drawn.program), tmp_path_factory.mktemp("program"))
    assert (check(drawn.program) == ()) == (found.code == 0), found.said


@st.composite
def rewrites(draw: st.DrawFn) -> Instr:
    """An instruction in exactly the silent-rewrite sets of design section 4."""
    if draw(st.booleans()):
        imms = st.one_of(
            st.integers(1, 4095).map(lambda k: 4096 * k),
            st.integers(-4095, -1),
            st.integers(1, 4095).map(lambda k: -4096 * k),
        )
        return replace(draw(add_sub_imm("sp")), imm=draw(imms), lsl12=False)
    i = draw(load_store().filter(lambda i: isinstance(i.addr, Offset)))
    imm = draw(st.integers(-256, 255).filter(partial(rewrites_offset, size=i.op.size)))
    return LoadStore(i.op, i.rt, Offset(i.addr.rn, imm))


def add(imm: int) -> AddSubImm:
    """`add x1, x2, #imm`."""
    return AddSubImm(OpAddSub.ADD, Width.W64, Reg.X1, Reg.X2, imm, lsl12=False)


def ldr(op: OpLoadStore, imm: int) -> LoadStore:
    """`op x1, [x2, #imm]` (w1 for the byte loads)."""
    return LoadStore(op, Reg.X1, Offset(Reg.X2, imm))


@settings(backend="hypothesis")
@example(instr=add(4096))
@example(instr=add(-1))
@example(instr=ldr(OpLoadStore.LDR_X, 3))
@example(instr=ldr(OpLoadStore.LDR_X, -8))
@given(instr=rewrites())
def test_llvm_mc_rewrites_what_the_checker_refuses(
    tmp_path_factory: pytest.TempPathFactory, worker_id: str, instr: Instr
) -> None:
    """[law: no-silent-rewrite] For AddSubImm with imm = 4096 k (1 <= k <= 4095), imm in
    [-4095, -1] or imm = -4096 k, and unsigned offsets in [-256, 255] negative or not a
    multiple of the size, check reports IMM12 or OFFSET, llvm-mc exits 0, and the disassembly
    differs from the printed line."""
    assert {p.kind for p in check((instr,))} & {Kind.IMM12, Kind.OFFSET}
    tools = toolchain(tmp_path_factory, worker_id)
    text = print_program((instr,))
    assert disassemble(tools, text, tmp_path_factory.mktemp("rewrite")) != text.splitlines()


@pytest.mark.parametrize(
    ("instr", "refused"),
    [
        (add(4097), True),
        (ldr(OpLoadStore.LDR_X, 257), True),
        (ldr(OpLoadStore.LDRB, 4096), True),
        (add(4095), False),
        (ldr(OpLoadStore.LDR_X, 8 * 4095), False),
        (ldr(OpLoadStore.LDRB, 4095), False),
    ],
)
def test_past_the_rewrite_sets_both_refuse_and_at_the_boundaries_neither(
    tmp_path_factory: pytest.TempPathFactory, worker_id: str, instr: Instr, refused: bool
) -> None:
    tools = toolchain(tmp_path_factory, worker_id)
    found = verdict(tools, print_program((instr,)), tmp_path_factory.mktemp("edge"))
    assert found.lines == ({1} if refused else set()), found.said
    assert (check((instr,)) != ()) == refused
