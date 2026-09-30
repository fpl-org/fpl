"""fpl/lower starts from the core AST: nothing of the surface, the parser or the driver."""

import ast
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

LOWER = Path(__file__).parent.parent / "fpl" / "lower"
FORBIDDEN = (
    "fpl.parse",
    "fpl.desugar",
    "fpl.ast_surface",
    "fpl.driver",
    "fpl.repl",
    "fpl.__main__",
    "lark",
    "fpl.asm",
)


def imported(tree: ast.Module) -> list[str]:
    """Every module `tree` imports, relative imports resolved from inside fpl.lower, and each
    name a `from` import takes as a module of its own (`from fpl import parse`)."""
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            package = ["fpl", "lower"][: max(0, 3 - node.level)] if node.level else []
            base = ".".join([*package, *([node.module] if node.module else [])])
            found += [base, *(f"{base}.{alias.name}" for alias in node.names)]
    return found


def forbidden(module: str) -> bool:
    return any(module == f or module.startswith(f"{f}.") for f in FORBIDDEN)


@given(st.sampled_from(sorted(LOWER.glob("*.py"))))
def test_lower_boundary(path: Path) -> None:
    """[law: lower-boundary] Every module under `fpl/lower` imports none of `fpl.parse`,
    `fpl.desugar`, `fpl.ast_surface`, `fpl.driver`, `fpl.repl`, `fpl.__main__`, `lark`,
    `fpl.asm`."""
    modules = imported(ast.parse(path.read_text(encoding="utf-8")))
    assert [m for m in modules if forbidden(m)] == []


def test_a_surface_import_is_caught() -> None:
    tree = ast.parse("from .. import parse\nimport lark.lexer\nfrom fpl.eval import held\n")
    assert [m for m in imported(tree) if forbidden(m)] == ["fpl.parse", "lark.lexer"]
