"""`python -m fpl file.fpl` runs a file."""

import sys
from functools import partial
from pathlib import Path

from fpl.driver import run
from fpl.errors import FplError


def main(argv: list[str]) -> int:
    """Run the file named in argv and print its output, or the one error line; 0 means it ran.

    Goals go to stderr, before anything runs. The error line goes to stdout, where an
    `.expected` file compares it; the source line and the caret under the column go to stderr,
    for the operator reading the terminal."""
    if len(argv) != 1:
        print("usage: python -m fpl <file.fpl>", file=sys.stderr)
        return 2
    source = Path(argv[0]).read_text()
    try:
        print(run(source, partial(print, file=sys.stderr)), end="")
    except FplError as error:
        print(error)
        shown = error.render(source).partition("\n")[2]
        if shown:
            print(shown, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
