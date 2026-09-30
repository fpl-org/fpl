"""fpl.asm.aarch64 is free of FPL: it imports the standard library, icontract and fpl.asm.

The import-linter contract `asm-stands-alone` forbids the rest of fpl; this walk also refuses
third-party packages other than icontract, and names the file and the import it refuses.
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

# The checkout's sources, not the test file's parent: under mutmut the tests run from mutants/,
# whose rewritten copies import mutmut's trampoline, and the law is about the code as written.
ROOT = Path(
    subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=Path(__file__).parent,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
)
FILES = sorted((ROOT / "fpl" / "asm" / "aarch64").rglob("*.py"))
ALLOWED = sys.stdlib_module_names | {"icontract"}


def imported(node: ast.Import | ast.ImportFrom, package: str) -> list[str]:
    """The absolute module names `node` imports, relative ones resolved against `package`."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    base = package.split(".")[: len(package.split(".")) + 1 - node.level] if node.level else []
    return [".".join([*base, *filter(None, [node.module])])]


def foreign(source: str, package: str) -> list[str]:
    """The modules `source`, a module of `package`, imports from outside what fpl.asm may use."""
    names = [
        name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import | ast.ImportFrom)
        for name in imported(node, package)
    ]
    return [
        name
        for name in names
        if name.split(".")[0] not in ALLOWED
        and name != "fpl.asm"
        and not name.startswith("fpl.asm.")
    ]


def refused(path: Path, root: Path = ROOT) -> list[str]:
    """One `<file>: imports <module>` line per import of `path` that fpl.asm may not make."""
    package = ".".join(path.parent.relative_to(root).parts)
    return [
        f"{path.relative_to(root)}: imports {name}" for name in foreign(path.read_text(), package)
    ]


@given(st.sampled_from(FILES))
def test_every_module_imports_only_the_stdlib_icontract_and_fpl_asm(path: Path) -> None:
    """[law: fpl-free] Every import in fpl/asm/aarch64/**/*.py is stdlib, icontract, or fpl.asm."""
    assert refused(path) == []


@pytest.mark.parametrize(
    ("source", "name"),
    [
        ("import fpl.parse", "fpl.parse"),
        ("from fpl import driver", "fpl"),
        ("from ... import eval", "fpl"),
        ("from ...errors import Span", "fpl.errors"),
        ("import hypothesis.strategies", "hypothesis.strategies"),
        ("import fpl.asmx", "fpl.asmx"),
    ],
)
def test_a_foreign_import_is_refused_naming_the_file_and_the_import(
    tmp_path: Path, source: str, name: str
) -> None:
    path = tmp_path / "fpl" / "asm" / "aarch64" / "bad.py"
    path.parent.mkdir(parents=True)
    path.write_text(f"import re\n{source}\n")
    assert refused(path, tmp_path) == [f"fpl/asm/aarch64/bad.py: imports {name}"]


@pytest.mark.parametrize(
    "source",
    [
        "import re",
        "from dataclasses import dataclass",
        "import icontract",
        "from . import model",
        "from .model import Reg",
        "from .. import aarch64",
        "from fpl.asm.aarch64.model import Reg",
    ],
)
def test_the_stdlib_icontract_and_fpl_asm_itself_are_allowed(source: str) -> None:
    assert foreign(source, "fpl.asm.aarch64") == []
