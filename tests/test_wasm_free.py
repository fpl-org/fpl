"""fpl.asm stands on its own: it imports the standard library, icontract and fpl.asm only.

quality/importlinter.ini's contract asm-stands-alone is the gate for imports of the rest of
fpl; this law also refuses a third-party package other than icontract, which no contract names.
"""

import ast
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

import fpl.asm

ASM = Path(fpl.asm.__file__).parent
MODULES = sorted(ASM.rglob("*.py"))
FOREIGN = [
    "import lark",
    "import fpl.types",
    "from fpl import eval",
    "from fpl.parse import parse",
    "from ...parse import parse",
]


def package(path: Path) -> str:
    """The dotted package a module file's relative imports resolve against."""
    parts = path.relative_to(ASM.parent.parent).with_suffix("").parts
    return ".".join(parts[:-1])


def imported(source: str, package: str) -> set[str]:
    """Every module `source` imports, its relative imports resolved against `package`."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = package.split(".")[: len(package.split(".")) - node.level + 1]
            names.add(".".join([*(base if node.level else []), *filter(None, [node.module])]))
    return names


def allowed(name: str) -> bool:
    """Whether fpl.asm may import the module `name`."""
    top = name.split(".", maxsplit=1)[0]
    own = name == "fpl.asm" or name.startswith("fpl.asm.")
    return top in sys.stdlib_module_names or top == "icontract" or own


@given(st.sampled_from(MODULES), st.sampled_from(FOREIGN))
def test_fpl_asm_imports_only_the_standard_library_icontract_and_itself(
    path: Path, foreign: str
) -> None:
    """[law: fpl-free] Every module under fpl/asm imports only stdlib, icontract and fpl.asm.*.

    Each module passes, and the same module with a foreign import added does not, so the check
    is shown to bite on relative imports too.
    """
    for module in MODULES:
        assert all(map(allowed, imported(module.read_text(), package(module)))), module
    assert not all(map(allowed, imported(path.read_text() + "\n" + foreign, package(path))))
