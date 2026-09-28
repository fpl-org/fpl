"""The grammar parses without an Earley ambiguity (docs/STACK.md): the whole example corpus,
and programs Hypothesis derives from the grammar itself, which reach the corners no example
was written for."""

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.extra.lark import from_lark
from lark import Token, Tree

from fpl.parse import GRAMMAR, parse, parser

CORPUS = sorted(Path(__file__).parent.parent.glob("features/*/examples/*.fpl"))
no_grammar = pytest.mark.skipif(not GRAMMAR.is_file(), reason="no grammar yet")


def ambiguous(tree: Tree[Token]) -> bool:
    """Whether Lark left an `_ambig` node anywhere in the tree."""
    return any(node.data == "_ambig" for node in tree.iter_subtrees())


@no_grammar
@pytest.mark.parametrize("program", CORPUS, ids=[p.stem for p in CORPUS])
def test_no_ambiguity_in_the_corpus(program: Path) -> None:
    assert not ambiguous(parse(program.read_text()))


@no_grammar
@pytest.mark.obligation("programs derived from the grammar parse without ambiguity")
@given(st.data())
def test_no_ambiguity_in_programs_derived_from_the_grammar(data: st.DataObject) -> None:
    program = data.draw(from_lark(parser()))  # drawn here, since the grammar may not exist
    assert not ambiguous(parse(program))
