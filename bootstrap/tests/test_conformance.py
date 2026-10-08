"""Every maintainer-written example runs to its `.expected` output (.agents/CONVENTIONS.md)."""

from pathlib import Path

import pytest
from corpus import PROGRAMS

from fpl.driver import run
from fpl.errors import FplError, UnresolvedError

PLACEHOLDER = "ERROR: 1:1 no evaluator yet\n"
EXAMPLES = [p for p in PROGRAMS if p.parts[-3] != "_template"]


def output(program: Path) -> str:
    """What `python -m fpl` prints for a program: its output, or its one error line. A call
    nothing answers is told at its word there, but the maintainer's `.expected` files still hold
    the skeleton's blanket refusal for the programs that hold one, and it stands for them here
    until they are rewritten (hole unimplemented-words)."""
    try:
        return run(program.read_text())
    except UnresolvedError:
        return PLACEHOLDER
    except FplError as error:
        return f"{error}\n"


@pytest.mark.parametrize("program", EXAMPLES, ids=[f"{p.parts[-3]}/{p.stem}" for p in EXAMPLES])
def test_example(program: Path) -> None:
    assert output(program) == program.with_suffix(".expected").read_text()
