"""Parsing either gives a tree or fails as an FplError inside the source, never otherwise."""

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fpl.errors import FplError, Span
from fpl.parse import parse, within

# A grammar for the tests only; the language's own is the maintainer's (fpl/grammar.lark).
WORDS = "start: WORD+\n%import common.WORD\n%import common.WS\n%ignore WS\n"


@pytest.fixture(scope="module")
def words(tmp_path_factory: pytest.TempPathFactory) -> Path:
    grammar = tmp_path_factory.mktemp("grammar") / "words.lark"
    grammar.write_text(WORDS)
    return grammar


def test_without_a_grammar_parsing_says_so(tmp_path: Path) -> None:
    with pytest.raises(FplError, match="no grammar yet"):
        parse("anything", tmp_path / "missing.lark")


def failure(source: str, grammar: Path) -> FplError | None:
    """The error parsing gives, or None when it parses."""
    try:
        parse(source, grammar)
    except FplError as error:
        return error
    return None


@given(st.text(alphabet="ab \n1", max_size=40))
def test_any_text_parses_or_fails_inside_it(words: Path, source: str) -> None:
    error = failure(source, words)
    if error is not None:
        lines = source.split("\n")
        assert 1 <= error.span.line <= len(lines)
        assert 1 <= error.span.col <= len(lines[error.span.line - 1]) + 1


def test_words_parse(words: Path) -> None:
    assert failure("a b", words) is None


def test_an_error_points_at_the_character(words: Path) -> None:
    error = failure("ab !", words)
    assert error is not None
    assert (error.span, error.message) == (Span(1, 4), "unexpected input")


def test_an_early_end_points_just_past_the_last_character(tmp_path: Path) -> None:
    two = tmp_path / "two.lark"
    two.write_text('start: "a" NL "a"\nNL: "\\n"\n')
    ends = {source: failure(source, two) for source in ("a", "a\n")}
    assert {source: error and error.span for source, error in ends.items()} == {
        "a": Span(1, 2),
        "a\n": Span(2, 1),
    }


@given(st.text(alphabet="ab\n", max_size=20), st.integers(-2, 6))
def test_within_names_a_character_or_the_position_just_past_a_line(source: str, line: int) -> None:
    lines = source.split("\n")
    on_a_line = line in range(1, len(lines) + 1)
    width = len(lines[line - 1]) if on_a_line else 0
    # Every column around the line, not a drawn one: the edge at width + 1 is the whole point,
    # and a random draw misses it often enough to let a mutant of the edge live.
    for col in range(-1, width + 4):
        assert within(source, line, col) == (on_a_line and 1 <= col <= width + 1)
