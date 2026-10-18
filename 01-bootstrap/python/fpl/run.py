"""
# Run

``` run = lex >> parse >> resolve >> expand >> elaborate >> lower >>
evaluate ```

The executable chain is the prefix the walker actually runs. `desugar`
stands in for resolve, expand, and lower.
"""

from fpl.ast_core import Run
from fpl.desugar import desugar, listing
from fpl.elaborate import elaborate
from fpl.errors import FplError
from fpl.evaluate import evaluate
from fpl.lex import lex
from fpl.parse import parse
from fpl.print import render

run_now = lex >> parse >> desugar >> elaborate >> evaluate

INDENT_COLUMNS = 4


def _notebook_indent(source: str) -> str:
    """
    Turn leading spaces into tabs for notebook editors that indent with
    spaces.

    Uses ceiling division by INDENT_COLUMNS so two spaces still become
    one tab.
    """
    lines: list[str] = []
    for line in source.split("\n"):
        n = 0
        while n < len(line) and line[n] == " ":
            n += 1
        if n == 0:
            lines.append(line)
            continue
        levels = (n + INDENT_COLUMNS - 1) // INDENT_COLUMNS
        lines.append("\t" * levels + line[n:])
    return "\n".join(lines)


def _run(source: str, session: str) -> str:
    """
    Render one program. `session` is accepted and not stored.
    """
    del session
    return render(listing(run_now(_notebook_indent(source))))


class Session:
    """
    A named run. The name is kept and not stored beyond the object.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    def file(self, path: str) -> str:
        """
        Read a file as UTF-8 and render it.
        """
        source = open(path, encoding="utf-8").read()
        return _run(source, self.name)

    def src(self, source: str) -> str:
        """
        Render a source string.
        """
        return _run(source, self.name)


default = Session("default")


def run_file(path: str) -> int:
    """
    Run one file the way the seed walker does. Goals go to stderr.
    """
    try:
        text = default.file(path)
    except FplError as error:
        print(error)
        return 1
    print(text, end="")
    return 0
