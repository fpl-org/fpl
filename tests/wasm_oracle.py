"""The oracles of fpl.asm.wasm: wabt 1.0.41 and wasmtime 45.0.2, from the dev shell's wasm layer.

Resolution. `resolve` runs RESOLVE once, from this file's directory, so the flake it enters is
the worktree's own (from mutmut's mutants/ copy too, which lives inside the checkout), and
flake.lock pins the versions. It reads stdout only and requires exactly one line per tool, in
the order asked, each starting with /nix/store/: the count and the prefix are the check, not the
exit status of `command -v`, since a tool missing from the layer prints no line and the shell
hook may print to stdout. wast2json, spectest-interp and wasm-validate sit beside wat2wasm in
wabt's bin. Both versions are checked, and every binary is called by its absolute path. Without
nix, resolving raises OracleError with the command it tried: an error, never a skip.

Batches. One .wast script holds a batch of items, each a module with what is expected of it, in
one of two dialects: wabt 1.0.41 has no `module definition`, so its verdicts are all
`(assert_invalid (module ...) "")`, which a valid module fails; wasmtime compiles a module
claimed valid as a `module definition` and asserts one claimed invalid invalid. Runs are
`assert_return` or `assert_trap` on `(invoke "main")` in both, and an exported global is read by
`(assert_return (get "g") ...)`, which both engines answer after a trap too. Every wabt tool
that reads a tail call gets --enable-tail-call; wasmtime 45 needs no flag.

Verdicts. A runner reports the indices of the items its engine disagreed with, found by mapping
a line of the script back to the item that holds it. wabt: a malformed token makes wast2json
reject the whole script at `batch.wast:L:C`; otherwise spectest-interp reports every directive
as `batch.wast:L: <message>`, a pass as `<directive> passed`, and its exit code, the failure
count modulo 256, is ignored. wasmtime stops at its first failing directive, naming
`batch.wast:L` for a failed directive and a malformed token alike.
"""

import functools
import re
import subprocess
import tempfile
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, assert_never

from fpl.asm.wasm.types import NumType

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
        wat2wasm,
        wabt / "wast2json",
        wabt / "spectest-interp",
        wabt / "wasm-validate",
        wasmtime,
    )
    every = (
        tools.wat2wasm,
        tools.wast2json,
        tools.spectest_interp,
        tools.wasm_validate,
        wasmtime,
    )
    missing = [str(path) for path in every if not path.is_file()]
    if missing or versions(tools) != VERSIONS:
        raise OracleError(f"{command}\nmissing: {missing}\nversions: {versions(tools)}")
    return tools


@functools.cache
def pinned() -> Tools:
    """The pinned oracles, resolved by RESOLVE at most once per process: the session fixture's
    value, so a second resolution is a cache hit, never a second `nix develop`."""
    return resolve()


def _run(cwd: str, *argv: str | Path) -> subprocess.CompletedProcess[str]:
    """`argv` run in `cwd`, its output captured as text; the exit status is the caller's to read."""
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)


def wat2wasm(tools: Tools, text: str) -> subprocess.CompletedProcess[str]:
    """wat2wasm, tail calls enabled, run on `text` as a .wat file; the binary is dropped."""
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "m.wat").write_text(text)
        return _run(tmp, tools.wat2wasm, "--enable-tail-call", "m.wat", "-o", "m.wasm")


@dataclass(frozen=True)
class Run:
    """A module, and what `(invoke "main")` gives: typed results, or the message of a trap."""

    module: str
    expect: tuple[tuple[NumType, int], ...] | str


@dataclass(frozen=True)
class Verdict:
    """A module, and whether it is claimed valid."""

    module: str
    valid: bool


@dataclass(frozen=True)
class Invoke:
    """An exported function called on typed arguments, and what it gives, as `Run.expect`."""

    name: str
    args: tuple[tuple[NumType, int], ...]
    expect: tuple[tuple[NumType, int], ...] | str


@dataclass(frozen=True)
class Get:
    """An exported global, and the typed value it holds."""

    name: str
    expect: tuple[NumType, int]


@dataclass(frozen=True)
class Calls:
    """A module, and the invocations and global reads checked against it in order: one item,
    many directives."""

    module: str
    invokes: tuple[Invoke | Get, ...]


Item = Run | Verdict | Calls
Dialect = Literal["wabt", "wasmtime"]
BATCH = "batch.wast"
LINE = re.compile(r"batch\.wast:(\d+)")
DIRECTIVE = re.compile(r"^batch\.wast:(\d+): (.*)$", re.MULTILINE)
PASSED = re.compile(r"\w+ passed")
SUMMARY = re.compile(r"^\d+/\d+ tests passed\.$", re.MULTILINE)


@dataclass(frozen=True)
class Report:
    """The indices of the items an engine disagreed with, and its output to show why."""

    wrong: tuple[int, ...]
    output: str


def _values(typed: tuple[tuple[NumType, int], ...]) -> str:
    """Typed values as constants, space-separated."""
    return " ".join(f"({t}.const {value})" for t, value in typed)


def _invoke(call: Invoke | Get) -> str:
    """The directive that checks what the invocation gives, or what the global holds."""
    if isinstance(call, Get):
        return f'(assert_return (get "{call.name}") {_values((call.expect,))})\n'
    action = f'(invoke "{call.name}" {_values(call.args)})'
    if isinstance(call.expect, str):
        return f'(assert_trap {action} "{call.expect}")\n'
    return f"(assert_return {action} {_values(call.expect)})\n"


def directives(item: Item, dialect: Dialect) -> str:
    """One item as .wast directives in `dialect`, ending in a newline."""
    match item:
        case Run():
            return item.module + _invoke(Invoke("main", (), item.expect))
        case Calls():
            return item.module + "".join(map(_invoke, item.invokes))
        case Verdict(valid=True) if dialect == "wasmtime":
            return "(module definition" + item.module.removeprefix("(module")
        case Verdict():
            return f'(assert_invalid {item.module} "")\n'
        case _:
            assert_never(item)


def write_batch(items: list[Item], dialect: Dialect) -> tuple[str, list[int]]:
    """The script of a batch, and the line on which each item starts."""
    parts: list[str] = []
    starts: list[int] = []
    line = 1
    for item in items:
        starts.append(line)
        parts.append(directives(item, dialect))
        line += parts[-1].count("\n")
    return "".join(parts), starts


def _located(output: str, starts: list[int]) -> tuple[int, ...]:
    """The index of the item holding the first `batch.wast:L` that `output` names."""
    found = LINE.search(output)
    if found is None:
        raise OracleError(f"no batch.wast line in:\n{output}")
    return (bisect_right(starts, int(found[1])) - 1,)


def _commas(json: str) -> str:
    """wast2json's output with the comma it leaves out put back: 1.0.41 writes an assert_trap's
    expected list of two or more types as `[{...}{...}]`, which spectest-interp refuses. `}{`
    occurs nowhere else, as no string in a batch's JSON holds a brace."""
    return json.replace("}{", "},{")


def run_wabt(tools: Tools, items: list[Item]) -> Report:
    """The items wast2json and spectest-interp disagree with; OracleError when spectest-interp
    writes to stderr or ends without its `N/M tests passed.` line, as it then has not run the
    batch and an empty verdict would pass every item."""
    text, starts = write_batch(items, "wabt")
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, BATCH).write_text(text)
        assembled = _run(tmp, tools.wast2json, "--enable-tail-call", BATCH, "-o", "batch.json")
        if assembled.returncode != 0:
            return Report(_located(assembled.stderr, starts), assembled.stderr)
        json = Path(tmp, "batch.json")
        json.write_text(_commas(json.read_text()))
        interp = _run(tmp, tools.spectest_interp, "--enable-tail-call", "batch.json")
    if interp.stderr or not SUMMARY.search(interp.stdout):
        raise OracleError(
            f"spectest-interp did not run the batch, no N/M tests passed:\n"
            f"{interp.stdout}{interp.stderr}"
        )
    failed = {
        bisect_right(starts, int(line)) - 1
        for line, message in DIRECTIVE.findall(interp.stdout)
        if not PASSED.match(message)
    }
    # A valid module fails its assert_invalid: that failure is wabt saying "valid".
    claims = [isinstance(item, Verdict) and item.valid for item in items]
    wrong = tuple(k for k, claim in enumerate(claims) if (k in failed) != claim)
    return Report(wrong, interp.stdout + interp.stderr)


def run_wasmtime(tools: Tools, items: list[Item]) -> Report:
    """The first item `wasmtime wast` disagrees with, if any."""
    text, starts = write_batch(items, "wasmtime")
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, BATCH).write_text(text)
        done = _run(tmp, tools.wasmtime, "wast", BATCH)
    if done.returncode == 0:
        return Report((), done.stderr)
    return Report(_located(done.stderr, starts), done.stderr)
