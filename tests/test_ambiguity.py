"""The grammar parses without an Earley ambiguity (docs/STACK.md). Programs Hypothesis derives
from the grammar reach the corners no example was written for; they are drawn from the grammar
with its blocks flattened, since an indenter cannot run inside a derivation. The corpus goes
through the LALR parser, which admits one tree or none (HOLES.md: ambiguity-over-flat)."""

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis.extra.lark import from_lark
from lark import Lark, Token, Tree

from fpl.ast_surface import Program
from fpl.parse import GRAMMAR, parse

CORPUS = sorted(Path(__file__).parent.parent.glob("features/*/examples/*.fpl"))
REWRITES = [
    ("line: frames _NL block?", "line: frames _NL"),
    ("block: _INDENT line+ _DEDENT\n", ""),
    ("%declare _INDENT _DEDENT\n", ""),
    (r"_NL: /(\r?\n\t*)+/", r"_NL: /\n/"),
    ("%ignore LCOMMENT\n", ""),
]


def flat(grammar: str) -> str:
    """The grammar with its blocks removed: a line is frames and a newline, comments are not
    ignored. Each rewrite must change the text, or the grammar has moved under this test."""
    for old, new in REWRITES:
        assert old in grammar, old
        grammar = grammar.replace(old, new)
    return grammar


FLAT = Lark(flat(GRAMMAR.read_text()), parser="earley", lexer="basic", ambiguity="explicit")


def ambiguous(tree: Tree[Token]) -> bool:
    """Whether Lark left an `_ambig` node anywhere in the tree."""
    return any(node.data == "_ambig" for node in tree.iter_subtrees())


@pytest.mark.parametrize("program", CORPUS, ids=[p.stem for p in CORPUS])
def test_the_corpus_parses_deterministically(program: Path) -> None:
    assert isinstance(parse(program.read_text()), Program)


@pytest.mark.obligation("programs derived from the grammar parse without ambiguity")
@given(from_lark(FLAT))
def test_no_ambiguity_in_programs_derived_from_the_grammar(program: str) -> None:
    assert not ambiguous(FLAT.parse(program))  # pyright: ignore[reportUnknownMemberType] -- lark types its text argument loosely
