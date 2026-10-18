"""
Project the literate pages to a Python package, stage mains, and Quarto
aliases.

The Markdown is the source. This writes 01-bootstrap/python/fpl/, and a
``.qmd`` symlink beside every page that holds a Marimo cell.
"""

from __future__ import annotations

import re
import shutil
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SEED = ROOT / "fpl"
OUT = ROOT / "python" / "fpl"
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
    "01.02-pass/01.02.01-lex.md": "lex/__init__.py",
    "01.02-pass/01.02.02-parse.md": "parse/__init__.py",
    "01.02-pass/01.02.05-desugar.md": "desugar/__init__.py",
    "01.02-pass/01.02.06-elaborate.md": "elaborate/__init__.py",
    "01.02-pass/01.02.10-evaluate.md": "evaluate/__init__.py",
    "01.01-boundary/01.01.02-fon.md": "fon/__init__.py",
    "01.01-boundary/01.01.03-pipe.md": "pipe/__init__.py",
    "01.01-boundary/01.01.01-source.md": "source.py",
    "01.01-boundary/01.01.04-render.md": "render.py",
    "01.04-compose/01.04.01-pass.md": "arrow.py",
    "01.04-compose/01.04.02-run.md": "run.py",
    "01.06-nagini/01.06.01-advance.md": "advance.py",
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

__all__ = ["desugar", "elaborate", "evaluate", "lex", "parse",
"run_file"]
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
    """A bare file runs in-process. Anything else is Click."""
    if (
        len(argv) == 1
        and argv[0] not in COMMANDS
        and Path(argv[0]).is_file()
    ):
        return run_file(argv[0])
    try:
        main(args=argv, standalone_mode=False)
    except SystemExit as stop:
        return int(stop.code or 0)
    return 0


if __name__ == "__main__":
    sys.exit(dispatch(sys.argv[1:]))
'''

STAGE_MAIN = """\
from fpl.pipe import cli

from . import {name}

cli({name})
"""


FRONT_MATTER = re.compile(r"\A---\n.*?\n---\n", re.S)


def quoted(prose: str) -> str:
    """
    A markdown stretch as a string statement. Python does not run it.
    """
    body = prose.strip("\n")
    if not body.strip():
        return ""
    wrapped: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if not buf:
            return
        paragraph = " ".join(part.strip() for part in buf)
        wrapped.extend(
            textwrap.wrap(
                paragraph,
                width=72,
                break_long_words=False,
                break_on_hyphens=False,
            )
            or [paragraph]
        )
        buf.clear()

    for line in body.split("\n"):
        if line.strip() == "":
            flush()
            wrapped.append("")
        else:
            buf.append(line)
    flush()
    while wrapped and wrapped[0] == "":
        wrapped.pop(0)
    while wrapped and wrapped[-1] == "":
        wrapped.pop()
    text = "\n".join(wrapped)
    if '"""' in text:
        return "'''\n" + text + "\n'''"
    return '"""\n' + text + '\n"""'


def cell(text: str) -> str:
    """
    Every code cell, in reading order, with the prose between them as
    string statements.

    A cell named setup is the notebook's `import marimo as mo`. A cell
    named play is for running a program in the notebook. Neither belongs
    in the module.
    """
    body = FRONT_MATTER.sub("", text, count=1)
    parts: list[str] = []
    cursor = 0
    saw = False
    for match in FENCE.finditer(body):
        prose = quoted(body[cursor : match.start()])
        if prose:
            parts.append(prose)
        name, source = match.group(1), match.group(2)
        if name not in {"setup", "play"}:
            parts.append(source.rstrip())
            saw = True
        cursor = match.end()
    tail = quoted(body[cursor:])
    if tail:
        parts.append(tail)
    if not saw:
        raise SystemExit("no python cell in a module page")
    return "\n\n".join(_one_docstring(parts)) + "\n"


def _one_docstring(parts: list[str]) -> list[str]:
    """
    Page prose and a cell's opening docstring are one string, then the
    imports.
    """
    if len(parts) < 2 or not parts[0].lstrip().startswith(('"""', "'''")):
        return parts
    code = parts[1].lstrip("\n")
    match = re.match(
        r'(?P<indent>[ \t]*)(?P<q>"""|\'\'\')(?P<body>.*?)(?P=q)\s*',
        code,
        re.S,
    )
    if match is None:
        return parts
    quote = '"""' if parts[0].lstrip().startswith('"""') else "'''"
    prose = parts[0].strip()
    prose = prose[len(quote) : -len(quote)].strip("\n")
    doc = match.group("body").strip("\n")
    merged = f"{quote}\n{prose}\n\n{doc}\n{quote}"
    rest = code[match.end() :].lstrip("\n")
    return [merged, rest, *parts[2:]] if rest else [merged, *parts[2:]]


def aliases() -> None:
    """
    Point ``name.qmd`` at every page Quarto should execute.
    """
    for path in ROOT.rglob("*.md"):
        if (
            ".vendor" in path.parts
            or "site" in path.parts
            or OUT in path.parents
        ):
            continue
        if "{.marimo" not in path.read_text():
            continue
        link = path.with_suffix(".qmd")
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(path.name)


def tangle() -> None:
    """
    Write the package from the pages and the seed's support modules.
    """
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
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
        "export PYTHONPATH="
        '"$lit/.vendor:$lit/python${PYTHONPATH:+:$PYTHONPATH}"\n'
        'exec "${FPL_PYTHON:-python3}" -m fpl "$@"\n'
    )
    (bin_dir / "fpl").chmod(0o755)


if __name__ == "__main__":
    tangle()
