"""Oracle: the tools come from the pin, and every other answer is an error, never a skip."""

import subprocess
from pathlib import Path

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st
from riscv_oracle import NAMES, VERSIONS, ToolchainError, parse_paths, resolve, toolchain

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
