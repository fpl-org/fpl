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
