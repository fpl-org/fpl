"""The oracles of fpl.asm.wasm: wabt 1.0.41 and wasmtime 45.0.2, from the dev shell's wasm layer.

Resolution. `resolve` runs RESOLVE once, from this file's directory, so the flake it enters is
the worktree's own (from mutmut's mutants/ copy too, which lives inside the checkout), and
flake.lock pins the versions. It reads stdout only and requires exactly one line per tool, in
the order asked, each starting with /nix/store/: the count and the prefix are the check, not the
exit status of `command -v`, since a tool missing from the layer prints no line and the shell
hook may print to stdout. wast2json, spectest-interp and wasm-validate sit beside wat2wasm in
wabt's bin. Both versions are checked, and every binary is called by its absolute path. Without
nix, resolving raises OracleError with the command it tried: an error, never a skip.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path

RESOLVE = (
    'nix develop "$(git rev-parse --show-toplevel)#wasm"'
    " -c bash -c 'command -v wat2wasm wasmtime'"
)
STORE = "/nix/store/"
VERSIONS = {"wat2wasm": "1.0.41", "wasmtime": "wasmtime 45.0.2"}


class OracleError(Exception):
    """An oracle could not be resolved or run; the message holds the command and its output."""


@dataclass(frozen=True)
class Tools:
    """The oracle binaries, each an absolute path into the Nix store."""

    wat2wasm: Path
    wast2json: Path
    spectest_interp: Path
    wasm_validate: Path
    wasmtime: Path


def store_paths(stdout: str) -> tuple[Path, Path] | None:
    """wat2wasm's and wasmtime's paths from RESOLVE's stdout; None unless it is exactly those."""
    lines = stdout.splitlines()
    if len(lines) != 2 or not all(line.startswith(STORE) for line in lines):
        return None
    return Path(lines[0]), Path(lines[1])


def versions(tools: Tools) -> dict[str, str]:
    """What `--version` prints for wat2wasm and wasmtime, stripped."""
    return {
        tool.name: subprocess.run(
            [tool, "--version"], capture_output=True, text=True, check=False
        ).stdout.strip()
        for tool in (tools.wat2wasm, tools.wasmtime)
    }


def resolve(command: str = RESOLVE) -> Tools:
    """The pinned oracles, by `command` run in bash from this directory; OracleError if not."""
    done = subprocess.run(
        ["bash", "-c", command],
        cwd=Path(__file__).parent,
        capture_output=True,
        text=True,
        check=False,
    )
    paths = store_paths(done.stdout)
    if paths is None:
        raise OracleError(f"{command}\nstdout:\n{done.stdout}\nstderr:\n{done.stderr}")
    wat2wasm, wasmtime = paths
    wabt = wat2wasm.parent
    tools = Tools(
        wat2wasm, wabt / "wast2json", wabt / "spectest-interp", wabt / "wasm-validate", wasmtime
    )
    every = (tools.wat2wasm, tools.wast2json, tools.spectest_interp, tools.wasm_validate, wasmtime)
    missing = [str(path) for path in every if not path.is_file()]
    if missing or versions(tools) != VERSIONS:
        raise OracleError(f"{command}\nmissing: {missing}\nversions: {versions(tools)}")
    return tools
