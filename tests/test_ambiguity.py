"""The grammar parses without an Earley ambiguity (docs/STACK.md). Programs Hypothesis derives
from the grammar reach the corners no example was written for; they are drawn from the grammar
with its blocks flattened, since an indenter cannot run inside a derivation (HOLES.md:
ambiguity-over-flat). The corpus is pre-lexed and read by Earley over the whole grammar with the
tab indenter, which keeps every derivation it finds."""

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis.extra.lark import from_lark
from lark import Lark, Token, Tree

from fpl.ast_surface import Program
from fpl.lex import prelex
from fpl.parse import GRAMMAR, FplIndenter, parse

CORPUS = sorted(Path(__file__).parent.parent.glob("features/*/examples/*.fpl"))
REWRITES = [
    ("line: frames _NL block?", "line: frames _NL"),
    ("block: _INDENT line+ _DEDENT\n", ""),
    ("%declare _INDENT _DEDENT\n", ""),
    (r"_NL: (/\r?\n\t*/ LCOMMENT?)+", r"_NL: /\n/"),
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
FULL = Lark(
    GRAMMAR.read_text(),
    parser="earley",
    lexer="basic",
    ambiguity="explicit",
    postlex=FplIndenter(),
)


def ambiguous(tree: Tree[Token]) -> bool:
    """Whether Lark left an `_ambig` node anywhere in the tree."""
    return any(node.data == "_ambig" for node in tree.iter_subtrees())


@pytest.mark.parametrize("program", CORPUS, ids=[p.stem for p in CORPUS])
def test_the_corpus_parses_without_ambiguity(program: Path) -> None:
    source = program.read_text()
    assert isinstance(parse(source), Program)
    assert not ambiguous(FULL.parse(prelex(source).code))  # pyright: ignore[reportUnknownMemberType] -- lark types its text argument loosely


@pytest.mark.obligation("programs derived from the grammar parse without ambiguity")
@given(from_lark(FLAT))
def test_no_ambiguity_in_programs_derived_from_the_grammar(program: str) -> None:
    assert not ambiguous(FLAT.parse(program))  # pyright: ignore[reportUnknownMemberType] -- lark types its text argument loosely
