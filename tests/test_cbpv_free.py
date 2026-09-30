"""fpl/cbpv stands alone: it imports the standard library, icontract and itself."""

import ast
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

CBPV = Path(__file__).parent.parent / "fpl" / "cbpv"
ALLOWED = frozenset(sys.stdlib_module_names) | {"icontract", "__future__"}


def imported(tree: ast.Module) -> list[str]:
    """Every module `tree` imports, relative imports resolved from inside fpl.cbpv."""
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            package = ["fpl", "cbpv"][: max(0, 3 - node.level)] if node.level else []
            found.append(".".join([*package, *([node.module] if node.module else [])]))
    return found


def allowed(module: str) -> bool:
    return module.split(".", maxsplit=1)[0] in ALLOWED or module.startswith("fpl.cbpv")


@given(st.sampled_from(sorted(CBPV.glob("*.py"))))
def test_cbpv_free(path: Path) -> None:
    """[law: cbpv-free] Every module under `fpl/cbpv` imports only the standard library,
    `icontract` and `fpl.cbpv.*`."""
    modules = imported(ast.parse(path.read_text(encoding="utf-8")))
    assert [m for m in modules if not allowed(m)] == []


def test_relative_imports_resolve() -> None:
    tree = ast.parse("from . import syntax\nfrom .. import eval\nimport os\n")
    assert imported(tree) == ["fpl.cbpv", "fpl", "os"]
    assert not allowed("fpl.eval")
