"""Not a test: the oracle tools, resolved from the `riscv` layer of the worktree's own flake.

`toolchain()` enters the layer's dev shell once per process (one per xdist worker) and asks
it where llvm-mc, llvm-objdump, ld.lld and qemu-system-riscv64 are; the versions are the ones
`flake.lock` pins. It reads stdout only: the flake's shell hook may print `==>` lines there
on a fresh clone, and a tool missing from the layer prints no line, so the check is four
lines, one per tool in the order asked, each a `/nix/store/` path ending in the tool's name,
not the exit status of `command -v`. Anything else is a `ToolchainError` showing the command,
its exit status, stdout and stderr. No `nix` is such an error too: an oracle that cannot run
fails the test, it never skips it. The tools are then called by absolute path.

`assemble`, `link`, `listing` (or `disassemble`) and `boot` run them with the design's fixed
flags on files in a work directory: `prog.s`, `prog.o`, `prog.elf`. `translate` runs the first
three on a source in a fresh work directory, each step only if the one before succeeded.
"""

import re
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from functools import cache
from pathlib import Path

HERE = Path(__file__).parent
NAMES = ("llvm-mc", "llvm-objdump", "ld.lld", "qemu-system-riscv64")
RESOLVE = "{nix} develop \"$(git rev-parse --show-toplevel)#riscv\" -c bash -c 'command -v {names}'"
TIMEOUT = 10  # seconds; a boot that outlasts it is a hang, reported as a failure
MC = ("-triple=riscv64", "-mattr=+m,-relax", "-filetype=obj")
LD = ("--no-relax", "-Ttext=0x80000000", "-e", "_start")
OBJDUMP = ("-d", "-M", "no-aliases", "-M", "numeric", "--no-print-imm-hex", "--mattr=+m")
QEMU = ("-M", "virt", "-bios", "none", "-nographic", "-monitor", "none", "-serial", "stdio")
# An instruction line of the disassembly: its hex address, the canonical text, and objdump's own
# symbolization of an absolute target (` <_start+0x18>`, printed after `jalr x0, -2048(x0)` and
# after a branch's address), which is a comment on the text, not part of it.
INSTRUCTION = re.compile(r"^\s*([0-9a-f]+):\s+(\S.*?)(?: <[^<>]*>)?$")
VERSIONS: dict[str, str] = dict(zip(NAMES, ("21.1.8", "21.1.8", "21.1.8", "10.2.4"), strict=True))


class ToolchainError(Exception):
    """The oracle tools could not be resolved, or are not the pinned versions."""


@dataclass(frozen=True, slots=True)
class Tools:
    """Absolute paths of the oracle tools, in the order of `NAMES`."""

    mc: Path
    objdump: Path
    lld: Path
    qemu: Path

    def by_name(self) -> dict[str, Path]:
        """Each tool's path under the name it was asked for."""
        return {
            "llvm-mc": self.mc,
            "llvm-objdump": self.objdump,
            "ld.lld": self.lld,
            "qemu-system-riscv64": self.qemu,
        }


def shown(command: str, done: subprocess.CompletedProcess[str]) -> str:
    """The command and everything it said, for an error message."""
    return (
        f"{command}\nexited {done.returncode}\n"
        f"--- stdout\n{done.stdout}--- stderr\n{done.stderr}--- end"
    )


def parse_paths(command: str, done: subprocess.CompletedProcess[str]) -> Tools:
    """The four paths `command` printed, or a `ToolchainError` showing all it said."""
    lines = done.stdout.splitlines()
    if len(lines) != len(NAMES) or not all(
        line.startswith("/nix/store/") and Path(line).name == name
        for line, name in zip(lines, NAMES, strict=False)
    ):
        raise ToolchainError(
            f"expected one /nix/store/ path per tool {NAMES} from\n" + shown(command, done)
        )
    return Tools(*(Path(line) for line in lines))


def resolve(nix: str = "nix") -> Tools:
    """Ask the `riscv` layer of the flake at the root of this checkout for the tools."""
    command = RESOLVE.format(nix=shlex.quote(nix), names=" ".join(NAMES))
    done = subprocess.run(
        ["bash", "-c", command], cwd=HERE, capture_output=True, text=True, check=False
    )
    return parse_paths(command, done)


def checked(tools: Tools) -> Tools:
    """`tools`, once each has reported its pinned version with `--version`."""
    for name, path in tools.by_name().items():
        done = subprocess.run(
            [path, "--version"], capture_output=True, text=True, check=False, timeout=10
        )
        if f" {VERSIONS[name]}" not in done.stdout:
            raise ToolchainError(
                f"{name} is not version {VERSIONS[name]}:\n" + shown(str(path), done)
            )
    return tools


@cache
def toolchain() -> Tools:
    """The pinned oracle tools, resolved and version-checked once per process."""
    return checked(resolve())


@dataclass(frozen=True, slots=True)
class Boot:
    """What a boot on QEMU virt showed: the UART's bytes, unchanged, and the exit status."""

    uart: bytes
    status: int


def run(*argv: str | Path) -> subprocess.CompletedProcess[str]:
    """Run a tool to completion within `TIMEOUT`, its output captured, its status unchecked."""
    return subprocess.run(argv, capture_output=True, text=True, check=False, timeout=TIMEOUT)


def assemble(tools: Tools, source: str, work: Path) -> subprocess.CompletedProcess[str]:
    """Assemble `source` into `work/prog.o`; the status and stderr say whether it could."""
    (work / "prog.s").write_text(source)
    return run(tools.mc, *MC, "-o", work / "prog.o", work / "prog.s")


def link(tools: Tools, work: Path) -> subprocess.CompletedProcess[str]:
    """Link `work/prog.o` at 0x80000000, entry `_start`, into `work/prog.elf`."""
    return run(tools.lld, *LD, "-o", work / "prog.elf", work / "prog.o")


def listing(tools: Tools, work: Path) -> list[tuple[int, str]]:
    """Each instruction in `work/prog.elf`: its address and its canonical text, in order.

    A branch's or jal's target is the absolute address objdump resolved, symbol comment removed.
    """
    done = run(tools.objdump, *OBJDUMP, "--no-show-raw-insn", work / "prog.elf")
    assert done.returncode == 0, shown("llvm-objdump", done)
    return [
        (int(m[1], 16), m[2]) for line in done.stdout.splitlines() if (m := INSTRUCTION.match(line))
    ]


def disassemble(tools: Tools, work: Path) -> list[str]:
    """The canonical text of each instruction in `work/prog.elf`, address column removed."""
    return [text for _, text in listing(tools, work)]


def boot(tools: Tools, work: Path) -> Boot:
    """Boot `work/prog.elf` bare on QEMU virt; a run past `TIMEOUT` raises, as a hang."""
    done = subprocess.run(
        [tools.qemu, *QEMU, "-kernel", work / "prog.elf"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        timeout=TIMEOUT,
    )
    return Boot(done.stdout, done.returncode)


@dataclass(frozen=True, slots=True)
class Translation:
    """What the tools made of a source: llvm-mc's run, then ld.lld's if llvm-mc accepted it.

    `listing` is the linked program's, empty unless both accepted it.
    """

    mc: subprocess.CompletedProcess[str]
    ld: subprocess.CompletedProcess[str] | None
    listing: tuple[tuple[int, str], ...] = ()

    @property
    def accepted(self) -> bool:
        """Whether llvm-mc and ld.lld both exited 0."""
        return self.mc.returncode == 0 and self.ld is not None and self.ld.returncode == 0


def translate(tools: Tools, source: str) -> Translation:
    """Assemble, link and list `source` in a fresh work directory, as far as each step succeeds."""
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        mc = assemble(tools, source, work)
        if mc.returncode != 0:
            return Translation(mc, None)
        ld = link(tools, work)
        return Translation(mc, ld, tuple(listing(tools, work)) if ld.returncode == 0 else ())
