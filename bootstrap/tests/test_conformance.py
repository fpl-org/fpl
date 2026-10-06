"""Every maintainer-written example runs to its `.expected` output (.agents/CONVENTIONS.md)."""

from pathlib import Path

import pytest
from corpus import PROGRAMS

from fpl.driver import run
from fpl.errors import FplError

EXAMPLES = [p for p in PROGRAMS if p.parts[-3] != "_template"]


def output(program: Path) -> str:
    """What `python -m fpl` prints for a program: its output, or its one error line."""
    try:
        return run(program.read_text())
    except FplError as error:
        return f"{error}\n"


@pytest.mark.parametrize("program", EXAMPLES, ids=[f"{p.parts[-3]}/{p.stem}" for p in EXAMPLES])
def test_example(program: Path) -> None:
    assert output(program) == program.with_suffix(".expected").read_text()
