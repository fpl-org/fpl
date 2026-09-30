"""HOLES.md is well formed: every entry has its four fields, and what it depends on exists.

An entry is a `## <name>` heading followed by `- <field>: <value>` lines. In the field
"Depends on it", a path is a token that contains `/` or ends in `.py` or `.md`; the rest is
prose and is ignored. A path may carry backticks, a trailing comma and a `:<line>` suffix.
"""

import re
import subprocess
from collections.abc import Callable
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

# The checkout, not this file's directory: under mutmut the tests run from mutants/, which
# holds no HOLES.md.
TOPLEVEL = Path(
    subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=Path(__file__).parent,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
)
FIELDS = ("Depends on it", "Default in force", "Closes by", "Evidence")
FIELD = re.compile(r"^- (?P<field>[^:]+): (?P<value>.*)$")
LINES = re.compile(r":\d+(-\d+)?$")

type Entry = dict[str, str]


def entries(text: str) -> dict[str, Entry]:
    """Every `## <name>` entry of `text`, with its fields by name."""
    out: dict[str, Entry] = {}
    fields: Entry = {}
    for line in text.splitlines():
        if line.startswith("## "):
            fields = out.setdefault(line.removeprefix("## ").strip(), {})
        elif m := FIELD.match(line):
            fields[m.group("field")] = m.group("value")
    return out


def paths(depends: str) -> list[str]:
    """The paths the field "Depends on it" names, stripped of backticks, commas and lines."""
    tokens = (LINES.sub("", t.strip("`,;()")) for t in depends.split())
    return [t for t in tokens if "/" in t or t.endswith((".py", ".md"))]


def problems(fields: Entry) -> list[str]:
    """What is wrong with one entry: a missing field, or a path that does not exist."""
    missing = [f"no field {f!r}" for f in FIELDS if f not in fields]
    named = paths(fields.get(FIELDS[0], ""))
    absent = [f"no path {p}" for p in named if not (TOPLEVEL / p).exists()]
    return missing + absent


def dropping(field: str) -> Callable[[Entry], Entry]:
    """A corruption that removes `field` from an entry."""
    return lambda fields: {k: v for k, v in fields.items() if k != field}


def depending_on(path: str) -> Callable[[Entry], Entry]:
    """A corruption that makes the entry depend on `path`, a file that does not exist."""
    return lambda fields: {**fields, FIELDS[0]: f"{fields[FIELDS[0]]}, {path}"}


HOLES = entries((TOPLEVEL / "HOLES.md").read_text())
# A path with a slash, and bare names a reader keeping only slashed paths would miss.
MISSING = ["tests/test_wasm_nowhere.py", "nowhere.py", "nowhere.md"]
CORRUPTIONS = [*map(dropping, FIELDS), *map(depending_on, MISSING)]


@given(st.sampled_from(sorted(HOLES)), st.sampled_from(CORRUPTIONS))
def test_every_hole_is_well_formed(name: str, corrupt: Callable[[Entry], Entry]) -> None:
    """[law: holes-well-formed] Every entry of HOLES.md has the four fields, and every path its
    "Depends on it" names exists.

    Each entry passes, and the drawn entry with a field dropped or a missing path added does
    not, so the check is shown to bite.
    """
    assert {n: problems(f) for n, f in HOLES.items() if problems(f)} == {}
    assert problems(corrupt(HOLES[name]))


def test_paths_are_read_from_prose() -> None:
    depends = "fpl/asm/wasm/exec.py (Exhausted, DEPTH), `tests/wasm_oracle.py:12-30`, the D track"
    assert paths(depends) == ["fpl/asm/wasm/exec.py", "tests/wasm_oracle.py"]
    assert paths("exec.py (DEPTH), `HOLES.md`, the D track") == ["exec.py", "HOLES.md"]
