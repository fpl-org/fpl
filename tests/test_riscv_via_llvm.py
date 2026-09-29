"""Oracle: the tools come from the pin, and the printed text is what llvm-objdump prints."""

import subprocess
import tempfile
from pathlib import Path

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st
from riscv_oracle import (
    NAMES,
    VERSIONS,
    ToolchainError,
    assemble,
    disassemble,
    link,
    listing,
    parse_paths,
    resolve,
    toolchain,
)
from riscv_strategies import forward_branching, instructions
from riscv_virt import HEAD

from fpl.asm.riscv.model import (
    Bare,
    Branch,
    Fence,
    I,
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
from fpl.asm.riscv.text import print_program

GOOD = [f"/nix/store/0000-tool/bin/{name}" for name in NAMES]
# Lines a resolution may print that are not the answer: the shell hook's banner, a tool found
# outside the store, blank lines, and the right paths out of place.
NOISE = [*GOOD, "==> wiring the git hooks", f"/usr/bin/{NAMES[0]}", "", "/nix/store/x/bin/cc"]


@given(st.sampled_from(NAMES))
def test_each_tool_is_the_pinned_one_from_the_riscv_layer(name: str) -> None:
    """[law: tools-from-pin] Each tool is an absolute /nix/store path at its pinned version.

    Resolved once per process from the worktree's own flake (`nix develop <root>#riscv`),
    so every call after the first is the same object.
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


def test_one_store_path_per_tool_in_order_is_the_answer() -> None:
    done = subprocess.CompletedProcess(["bash"], 0, "".join(f"{line}\n" for line in GOOD), "")
    assert parse_paths("cmd", done).by_name() == {
        n: Path(p) for n, p in zip(NAMES, GOOD, strict=True)
    }


@given(st.lists(st.one_of(st.sampled_from(NOISE), st.text(max_size=12)), max_size=6))
def test_anything_else_is_an_error_that_shows_stdout_and_stderr(lines: list[str]) -> None:
    assume(lines != GOOD)
    stdout = "".join(f"{line}\n" for line in lines)
    done = subprocess.CompletedProcess(["bash"], 0, stdout, "said on stderr")
    with pytest.raises(ToolchainError) as error:
        parse_paths("cmd", done)
    assert stdout in str(error.value)
    assert "said on stderr" in str(error.value)


def test_no_nix_is_an_error_naming_the_command_not_a_skip() -> None:
    with pytest.raises(ToolchainError, match="/nonexistent/nix develop"):
        resolve(nix="/nonexistent/nix")


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
