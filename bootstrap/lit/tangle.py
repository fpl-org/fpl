"""Project the literate pages to a Python package, stage mains, and Quarto aliases.

The Markdown is the source. This writes bootstrap/lit/fpl/, which is gitignored, and a
``.qmd`` symlink beside every page that holds a Marimo cell.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SEED = ROOT.parent / "fpl"
OUT = ROOT / "fpl"
FENCE = re.compile(
    r"```python \{\.marimo(?: name=\"([^\"]+)\")?\}\n(.*?)```",
    re.S,
)

SUPPORT = (
    "errors.py",
    "ast_surface.py",
    "ast_core.py",
    "multihash.py",
    "print.py",
    "trivia.py",
    "eval.py",
    "grammar.lark",
)

MODULES = {
    "pass/lex.md": "lex/__init__.py",
    "pass/parse.md": "parse/__init__.py",
    "pass/desugar.md": "desugar/__init__.py",
    "pass/elaborate.md": "elaborate/__init__.py",
    "pass/evaluate.md": "evaluate/__init__.py",
    "boundary/fon.md": "fon/__init__.py",
    "boundary/pipe.md": "pipe/__init__.py",
    "boundary/source.md": "source.py",
    "boundary/render.md": "render.py",
    "compose/pass.md": "arrow.py",
    "compose/run.md": "run.py",
    "nagini/advance.md": "advance.py",
}

PACKAGES = ("lex", "parse", "desugar", "elaborate", "evaluate", "fon", "pipe")

INIT = '''\
"""The literate bootstrap, tangled from the Markdown pages."""

import fpl.trivia
from fpl.desugar import desugar
from fpl.elaborate import elaborate
from fpl.evaluate import evaluate
from fpl.lex import lex
from fpl.parse import parse
from fpl.run import run_file

__all__ = ["desugar", "elaborate", "evaluate", "lex", "parse", "run_file"]
'''

MAIN = '''\
"""`fpl <file>` runs in-process. `fpl <stage>` is one filter."""

import sys
from pathlib import Path

import click

from fpl.pipe import cli
from fpl.run import run_file

COMMANDS = ("source", "lex", "parse", "desugar", "elaborate", "eval", "render")


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx: click.Context) -> None:
    """Run a file, or one pass across a pipe."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        ctx.exit(2)


@main.command("run")
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
def run_command(file: str) -> None:
    """Run a file in-process. ABTs stay in this process."""
    sys.exit(run_file(file))


def _filter(name: str) -> click.Command:
    def command() -> None:
        sys.exit(cli(name))

    command.__name__ = name
    return click.command(name)(command)


for _name in COMMANDS:
    main.add_command(_filter(_name))


def dispatch(argv: list[str]) -> int:
    """A bare file argument is an in-process run. Anything else is Click."""
    if len(argv) == 1 and argv[0] not in COMMANDS and Path(argv[0]).is_file():
        return run_file(argv[0])
    try:
        main(args=argv, standalone_mode=False)
    except SystemExit as stop:
        return int(stop.code or 0)
    return 0


if __name__ == "__main__":
    sys.exit(dispatch(sys.argv[1:]))
'''

STAGE_MAIN = '''\
from fpl.pipe import cli
from . import {name}

cli({name})
'''


def cell(text: str) -> str:
    """The named Marimo cell, or the only cell."""
    found = FENCE.findall(text)
    if not found:
        raise SystemExit(f"no python cell in a module page")
    named = [body for name, body in found if name]
    return (named[0] if named else found[0][1]).rstrip() + "\n"


def aliases() -> None:
    """Point ``name.qmd`` at every page Quarto should execute."""
    for path in ROOT.rglob("*.md"):
        if ".vendor" in path.parts or "site" in path.parts or OUT in path.parents:
            continue
        if "{.marimo" not in path.read_text():
            continue
        link = path.with_suffix(".qmd")
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(path.name)


def tangle() -> None:
    """Write the package from the pages and the seed's support modules."""
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    for name in SUPPORT:
        shutil.copy(SEED / name, OUT / name)
    for page, dest in MODULES.items():
        target = OUT / dest
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(cell((ROOT / page).read_text()))
    for name in PACKAGES:
        (OUT / name / "__main__.py").write_text(STAGE_MAIN.format(name=name))
    (OUT / "__init__.py").write_text(INIT)
    (OUT / "__main__.py").write_text(MAIN)
    aliases()
    bin_dir = ROOT / "bin"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "fpl").write_text(
        "#!/bin/sh\n"
        'here=$(CDPATH= cd -- "$(dirname "$0")" && pwd)\n'
        'lit=$(CDPATH= cd -- "$here/.." && pwd)\n'
        'export PYTHONPATH="$lit/.vendor:$lit${PYTHONPATH:+:$PYTHONPATH}"\n'
        'exec "${FPL_PYTHON:-python3}" -m fpl "$@"\n'
    )
    (bin_dir / "fpl").chmod(0o755)


if __name__ == "__main__":
    tangle()
