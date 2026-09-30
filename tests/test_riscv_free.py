"""fpl.asm is free of FPL: it imports the standard library, icontract and itself, nothing else.

The import-linter contract `asm-stands-alone` forbids the rest of fpl; this walk also refuses
third-party packages other than icontract, and names the file and the import it refuses.
"""

import ast
import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

ROOT = Path(__file__).parent.parent
FILES = sorted((ROOT / "fpl" / "asm").rglob("*.py"))
ALLOWED = sys.stdlib_module_names | {"icontract"}
# mutmut writes this import into every module it copies to mutants/, where the mutation lane
# runs this test; the source tree never has it, and deptry refuses mutmut in fpl/ anyway.
MUTMUT = "mutmut.mutation.trampoline"


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
        and name not in {"fpl.asm", MUTMUT}
        and not name.startswith("fpl.asm.")
    ]


def refused(path: Path, root: Path = ROOT) -> list[str]:
    """One `<file>: imports <module>` line per import of `path` that fpl.asm may not make."""
    package = ".".join(path.parent.relative_to(root).parts)
    return [
        f"{path.relative_to(root)}: imports {name}" for name in foreign(path.read_text(), package)
    ]


@given(st.sampled_from(FILES))
def test_every_module_of_fpl_asm_imports_only_the_stdlib_icontract_and_fpl_asm(path: Path) -> None:
    """[law: fpl-free] Every import in fpl/asm/**/*.py is stdlib, icontract, or fpl.asm."""
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
        ("import mutmut", "mutmut"),
    ],
)
def test_a_foreign_import_is_refused_naming_the_file_and_the_import(
    tmp_path: Path, source: str, name: str
) -> None:
    path = tmp_path / "fpl" / "asm" / "riscv" / "bad.py"
    path.parent.mkdir(parents=True)
    path.write_text(f"import re\n{source}\n")
    assert refused(path, tmp_path) == [f"fpl/asm/riscv/bad.py: imports {name}"]


@pytest.mark.parametrize(
    "source",
    [
        "import re",
        "from dataclasses import dataclass",
        "import icontract",
        "from . import model",
        "from .model import Reg",
        "from .. import riscv",
        "from fpl.asm.riscv.model import R",
        "from mutmut.mutation.trampoline import wrap_in_trampoline",
    ],
)
def test_the_stdlib_icontract_and_fpl_asm_itself_are_allowed(source: str) -> None:
    assert foreign(source, "fpl.asm.riscv") == []
