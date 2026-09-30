"""Oracle tests against the pinned LLVM tools: first, that they are the pinned ones."""

import platform
import subprocess
from functools import cache
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
)
from aarch64_strategies import instructions, witnesses
from hypothesis import given, settings
from hypothesis import strategies as st

from fpl.asm.aarch64.model import Program
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
