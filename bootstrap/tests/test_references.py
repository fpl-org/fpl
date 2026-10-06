"""Every citation of an example program names one that exists.

The harness cites the maintainer's examples by name: HOLES.md, the docs and the test
docstrings point at a program as a path under `features/`, as `examples/<name>` or, with a
line, as `<name>:<line>`. A rename under `features/` leaves those citations pointing at
nothing, and nothing else notices. A bare name with no line is not taken as a citation:
`python -m fpl file.fpl` and a test's `tmp_path / "p.fpl"` name no example.
"""

import re
from pathlib import Path

from corpus import PROGRAMS, REPO

HERE = Path(__file__).parent.parent  # this project: bootstrap/, or mutmut's copy of it
NAMES = {p.name for p in PROGRAMS}
CITERS = sorted(
    [
        *REPO.glob("*.md"),
        *REPO.glob(".agents/*.md"),
        *REPO.glob("docs/**/*.md"),
        *REPO.glob("bootstrap/*.md"),
        *HERE.glob("tests/*.py"),
        *HERE.glob("fpl/**/*.py"),
    ]
)

# A full path, `examples/<name>`, or `<name>:<line>`; a glob or a brace never matches.
PATH = re.compile(r"\bfeatures/[\w.-]+/examples/[\w.-]+\.fpl\b")
NAME = re.compile(r"(?:\bexamples/([\w.-]+\.fpl)\b|(?<![\w./-])([\w.-]+\.fpl):\d)")


def dangling(text: str) -> list[str]:
    """The citations in `text` that name no example program."""
    paths = [m for m in PATH.findall(text) if not (REPO / m).is_file()]
    names = [a or b for a, b in NAME.findall(text) if (a or b) not in NAMES]
    return paths + names


def test_a_renamed_program_dangles() -> None:
    name = "gone.fpl"
    path = f"features/draft1/examples/{name}"
    assert dangling(f"{path}:3, {name}:3 and draft1.fpl:2") == [path, name, name]


def test_every_citation_names_a_program() -> None:
    found = {str(p.relative_to(REPO)): dangling(p.read_text(encoding="utf-8")) for p in CITERS}
    assert {p: d for p, d in found.items() if d} == {}
