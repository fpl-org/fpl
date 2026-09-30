"""Not a test: the oracle tools, from the `aarch64` layer of the worktree's own flake.

`toolchain(factory, worker_id)` resolves them once per test session, not once per xdist worker:
eight concurrent `nix develop` of one flake wait on each other's fetch lock (design section 7).
It follows pytest-xdist's recipe for a session fixture that runs once, with `fcntl.flock`: the
first worker to lock a file under `factory.getbasetemp().parent`, which the session's workers
share, enters the dev shell and writes the paths as JSON; the others wait on the lock and read
them. Without xdist (`worker_id == "master"`) it resolves directly and writes nothing, since
`getbasetemp().parent` is then shared by every session on the machine.

The route is `platform.system()`'s: on Darwin llvm-mc, llvm-objdump, ld64.lld and `$SDKROOT`
(the SDK comes from the shell's standard environment, not the layer); on Linux llvm-mc,
llvm-objdump, ld.lld and qemu-aarch64. It reads stdout only and keeps the lines that start with
`/nix/store/`: the flake's shell hook may print `==>` lines there on a first entry, and a tool
missing from the layer prints no line, so the check is the four basenames in the order asked.
Anything else, another platform, or no `nix`, is a `ToolchainError` showing what was tried and
said: an oracle that cannot run fails the test, it never skips it. The versions are the ones
`flake.lock` pins; the tools are then called by absolute path.
"""

import fcntl
import json
import platform
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import pytest

HERE = Path(__file__).parent
RESOLVE = '{nix} develop "$(git rev-parse --show-toplevel)#aarch64" -c bash -c {ask}'
ASK = {
    "Darwin": 'command -v llvm-mc llvm-objdump ld64.lld; printf "%s\\n" "$SDKROOT"',
    "Linux": "command -v llvm-mc llvm-objdump ld.lld qemu-aarch64",
}
NAMES = {
    "Darwin": ("llvm-mc", "llvm-objdump", "ld64.lld", "MacOSX.sdk"),
    "Linux": ("llvm-mc", "llvm-objdump", "ld.lld", "qemu-aarch64"),
}
LLVM = "21.1.8"
QEMU = "10.2.4"
SDK = "14.4"  # the SDK version the darwin link line names: -platform_version macos 14.0 14.4


class ToolchainError(Exception):
    """The oracle tools could not be resolved, or are not the pinned versions."""


@dataclass(frozen=True, slots=True)
class Tools:
    """The route's platform, the absolute paths of its four items, in the order of `NAMES`,
    and the seconds `nix develop` took to name them."""

    system: str
    mc: Path
    objdump: Path
    linker: Path
    host: Path  # Darwin: $SDKROOT, the SDK the link needs; Linux: qemu-aarch64, the runner
    seconds: float

    def paths(self) -> tuple[Path, Path, Path, Path]:
        """The four items, in the order asked."""
        return self.mc, self.objdump, self.linker, self.host


def shown(command: str, done: subprocess.CompletedProcess[str]) -> str:
    """The command and everything it said, for an error message."""
    return (
        f"{command}\nexited {done.returncode}\n"
        f"--- stdout\n{done.stdout}--- stderr\n{done.stderr}--- end"
    )


def command(system: str, nix: str = "nix") -> str:
    """The shell command that asks the `aarch64` layer for `system`'s tools."""
    if system not in ASK:
        raise ToolchainError(f"no aarch64 route for platform {system!r}: only Darwin or Linux")
    return RESOLVE.format(nix=shlex.quote(nix), ask=shlex.quote(ASK[system]))


def parse_paths(
    system: str, asked: str, done: subprocess.CompletedProcess[str]
) -> tuple[Path, ...]:
    """The `/nix/store/` lines of stdout, if they are `NAMES[system]` in order by basename."""
    lines = [line for line in done.stdout.splitlines() if line.startswith("/nix/store/")]
    if tuple(Path(line).name for line in lines) != NAMES[system]:
        raise ToolchainError(
            f"expected one /nix/store/ path each for {NAMES[system]}, in order, from\n"
            + shown(asked, done)
        )
    return tuple(Path(line) for line in lines)


def resolve(system: str, nix: str = "nix") -> Tools:
    """Ask the `aarch64` layer of the flake at the root of this checkout for the tools."""
    asked = command(system, nix)
    start = time.perf_counter()
    done = subprocess.run(
        ["bash", "-c", asked], cwd=HERE, capture_output=True, text=True, check=False
    )
    seconds = time.perf_counter() - start
    mc, objdump, linker, host = parse_paths(system, asked, done)
    return Tools(system, mc, objdump, linker, host, seconds)


def reported(tool: Path) -> str:
    """What `tool --version` printed."""
    done = subprocess.run(
        [tool, "--version"], capture_output=True, text=True, check=False, timeout=10
    )
    return done.stdout


def checked(tools: Tools) -> Tools:
    """`tools`, once llvm-mc, and qemu-aarch64 or the SDK, report their pinned versions."""
    found = {"llvm-mc": (reported(tools.mc), f"version {LLVM}")}
    if tools.system == "Linux":
        found["qemu-aarch64"] = (reported(tools.host), f"version {QEMU}")
    else:
        sdk = json.loads((tools.host / "SDKSettings.json").read_text())["Version"]
        found["MacOSX.sdk"] = (f"Version {sdk}", f"Version {SDK}")
    for name, (said, pinned) in found.items():
        if pinned not in said:
            raise ToolchainError(f"{name} is not {pinned}; it reports:\n{said}")
    return tools


def dump(tools: Tools) -> str:
    """`tools` as the JSON the first xdist worker shares with the others."""
    paths = [str(path) for path in tools.paths()]
    return json.dumps({"system": tools.system, "paths": paths, "seconds": tools.seconds})


def load(text: str) -> Tools:
    """The `Tools` that `dump` wrote."""
    shared = json.loads(text)
    mc, objdump, linker, host = (Path(path) for path in shared["paths"])
    return Tools(shared["system"], mc, objdump, linker, host, shared["seconds"])


def toolchain(factory: pytest.TempPathFactory, worker_id: str) -> Tools:
    """The pinned oracle tools of this platform's route, resolved once per test session."""
    return resolved(None if worker_id == "master" else factory.getbasetemp().parent)


@cache
def resolved(shared: Path | None) -> Tools:
    """The tools, resolved directly (`shared` None), or once for all the workers that share
    the directory `shared`: the first to take its lock resolves them, the rest read them."""
    if shared is None:
        return checked(resolve(platform.system()))
    with (shared / "aarch64-toolchain.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        found = shared / "aarch64-toolchain.json"
        if found.is_file():
            return load(found.read_text())
        tools = checked(resolve(platform.system()))
        found.write_text(dump(tools))
        return tools


# The run route, per platform: the object format the block is assembled for, and how the
# linked program is started. Darwin runs a Mach-O natively (arm64 macOS runs no static
# executables, so it links libSystem; the linker's default ad-hoc signature stays on, since an
# unsigned binary is killed); Linux runs a static ELF under qemu-aarch64.
TRIPLE = {"Darwin": "-triple=arm64-apple-macos14.0", "Linux": "-triple=aarch64-linux-gnu"}
TIMEOUT = 10  # seconds; a run that outlasts it is a hang, reported as a failure


def run(*argv: str | Path) -> subprocess.CompletedProcess[bytes]:
    """Run a tool or a program to completion within `TIMEOUT`, output captured, unchecked."""
    return subprocess.run(argv, capture_output=True, check=False, timeout=TIMEOUT)


def assemble(tools: Tools, source: str, work: Path) -> subprocess.CompletedProcess[bytes]:
    """Assemble `source` for the route's object format into `work/prog.o`."""
    (work / "prog.s").write_text(source)
    files = ("-o", work / "prog.o", work / "prog.s")
    return run(tools.mc, TRIPLE[tools.system], "-filetype=obj", *files)


def link(tools: Tools, work: Path) -> subprocess.CompletedProcess[bytes]:
    """Link `work/prog.o` into the executable `work/prog`, as the route links it."""
    out = ("-o", work / "prog", work / "prog.o")
    if tools.system == "Linux":
        return run(tools.linker, "-static", "-e", "_start", *out)
    sdk = ("-platform_version", "macos", "14.0", SDK, "-syslibroot", tools.host, "-lSystem")
    return run(tools.linker, "-arch", "arm64", *sdk, *out)


def execute(tools: Tools, work: Path) -> subprocess.CompletedProcess[bytes]:
    """Run `work/prog`: natively on Darwin, under qemu-aarch64 on Linux."""
    if tools.system == "Linux":
        return run(tools.host, work / "prog")
    return run(work / "prog")


# The text oracle: one triple on every host, never --mattr (an alias gated on a feature could
# print differently under another CPU), and llvm-objdump's default aliases (design section 3).
TEXT = "-triple=aarch64-linux-gnu"
DUMP = ("-d", "--no-show-raw-insn", "--no-leading-addr", "--no-print-imm-hex")


def disassemble(tools: Tools, source: str, work: Path) -> list[str]:
    """The lines llvm-objdump prints for `source` assembled with `TEXT`, normalised as
    print_program prints: symbol, header and blank lines dropped, `//` comments removed,
    the indent before the tab and trailing space stripped. AssertionError if llvm-mc fails."""
    (work / "text.s").write_text(source)
    made = run(tools.mc, TEXT, "-filetype=obj", "-o", work / "text.o", work / "text.s")
    assert made.returncode == 0, made.stderr.decode()
    dumped = run(tools.objdump, *DUMP, work / "text.o").stdout.decode()
    lines = (line.partition("//")[0].rstrip() for line in dumped.splitlines())
    return [line.lstrip(" ") for line in lines if line.startswith(" ")]


# The checker oracle: llvm-mc's exit status and the lines it reports errors on. A fixup or
# undefined-symbol error comes only once the program parsed; the latter has no line.
ERROR = re.compile(r"^[^\n:]+:(\d+):\d+: error: ", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class Verdict:
    """llvm-mc's exit status, the 1-based lines it reported errors on, and all it said."""

    code: int
    lines: frozenset[int]
    said: str


def verdict(tools: Tools, source: str, work: Path) -> Verdict:
    """Assemble `source` with the text triple, no linker, and read what llvm-mc refused."""
    (work / "check.s").write_text(source)
    done = run(tools.mc, TEXT, "-filetype=obj", "-o", work / "check.o", work / "check.s")
    said = done.stderr.decode()
    return Verdict(done.returncode, frozenset(int(n) for n in ERROR.findall(said)), said)
