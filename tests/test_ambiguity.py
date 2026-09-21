"""The grammar parses the whole example corpus without an Earley ambiguity (docs/STACK.md)."""

from pathlib import Path

import pytest
from lark import Token, Tree

from fpl.parse import GRAMMAR, parse

CORPUS = sorted(Path(__file__).parent.parent.glob("features/*/examples/*.fpl"))


def ambiguous(tree: Tree[Token]) -> bool:
    """Whether Lark left an `_ambig` node anywhere in the tree."""
    return any(node.data == "_ambig" for node in tree.iter_subtrees())


@pytest.mark.skipif(not GRAMMAR.is_file(), reason="no grammar yet")
@pytest.mark.parametrize("program", CORPUS, ids=[p.stem for p in CORPUS])
def test_no_ambiguity(program: Path) -> None:
    assert not ambiguous(parse(program.read_text()))
