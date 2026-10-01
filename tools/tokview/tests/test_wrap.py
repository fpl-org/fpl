"""The folding and ventilating laws of tokview.wrap."""

import re

from hypothesis import given
from hypothesis import strategies as st
from tokview.wrap import (
    LIST_NUMBER,
    TAB,
    cols,
    fold_line,
    folded,
    sentences,
    ventilated,
    wrap,
)

WORD = st.text(alphabet="abcxyz.,()→7", min_size=1, max_size=12)
TEXT = st.lists(WORD, min_size=1, max_size=30).map(" ".join)
INDENT = st.integers(0, 3).map(lambda n: "\t" * n)
CODE = st.tuples(INDENT, st.text(alphabet="abc :[]-+", min_size=1, max_size=60)).map("".join)
MARK = st.sampled_from([";;", ";;;", ";;;;"])
WIDTH = st.integers(20, 160)
PROSE = st.lists(
    st.sampled_from(["The", "note", "ends.", "Then", "e.g.", "a", "list", "—", "1.", "2.", "x;"]),
    min_size=1,
    max_size=25,
).map(" ".join)


def said(line: str) -> str:
    """The comment text of a folded line: what follows its first `; `."""
    return line.split("; ", 1)[1]


def visible(text: str) -> str:
    """Text without its whitespace."""
    return re.sub(r"\s", "", text)


@given(CODE, TEXT, WIDTH)
def test_a_folded_note_fits_unless_one_word_cannot(code: str, note: str, width: int) -> None:
    lines, over = fold_line(f"{code}\t; {note}", width)
    assert over == (cols(code) > width)
    for line in lines:
        assert cols(line) <= width or " " not in said(line)


@given(CODE, TEXT, WIDTH)
def test_a_folded_note_keeps_its_words(code: str, note: str, width: int) -> None:
    lines, _ = fold_line(f"{code}\t; {note}", width)
    assert lines[0].startswith(f"{code}\t; ")
    assert " ".join(said(line) for line in lines) == note


@given(INDENT, MARK, TEXT, WIDTH)
def test_a_comment_line_wraps_under_its_marker(
    indent: str, mark: str, text: str, width: int
) -> None:
    lines, over = fold_line(f"{indent}{mark} {text}", width)
    assert not over
    assert all(line.startswith(f"{indent}{mark} ") for line in lines)
    assert all(cols(line) <= width or " " not in said(line) for line in lines)
    assert " ".join(said(line) for line in lines) == text


@given(CODE, WIDTH)
def test_code_is_never_folded(code: str, width: int) -> None:
    assert fold_line(code, width) == ([code], cols(code) > width)


@given(st.lists(st.one_of(CODE, CODE.map(lambda c: c + "\t; note")), min_size=1), WIDTH)
def test_folded_counts_the_code_lines_over(lines: list[str], width: int) -> None:
    text, over = folded("\n".join(lines), width)
    assert over == sum(cols(line.split("\t; ")[0]) > width for line in lines)
    assert text.count("\n") >= len(lines) - 1


def test_a_note_that_fits_is_left_alone() -> None:
    assert fold_line("dup times\t; the square", 80) == (["dup times\t; the square"], False)


def test_an_empty_comment_survives() -> None:
    assert fold_line(";; ", 20) == ([";; "], False)
    assert wrap([], 20, 0) == [""]


def test_a_tab_is_four_columns() -> None:
    assert TAB == 4
    assert cols("\t\tab") == 10


@given(CODE, PROSE)
def test_ventilated_notes_keep_their_text(code: str, note: str) -> None:
    lines = ventilated(f"{code}\t; {note}").split("\n")
    assert lines[0].startswith(f"{code}\t; ")
    assert visible("".join(said(line) for line in lines)) == visible(note)


@given(INDENT, MARK, PROSE)
def test_ventilated_comments_keep_their_text(indent: str, mark: str, body: str) -> None:
    lines = ventilated(f"{indent}{mark} {body}").split("\n")
    assert all(line.startswith(f"{indent}{mark} ") for line in lines)
    assert visible("".join(said(line) for line in lines)) == visible(body)


@given(CODE)
def test_ventilating_leaves_code_alone(code: str) -> None:
    assert ventilated(code) == code


@given(PROSE)
def test_sentences_keep_the_text(note: str) -> None:
    assert visible("".join(sentences(note))) == visible(note)


@given(PROSE)
def test_a_list_number_never_stands_alone_before_its_item(note: str) -> None:
    parts = sentences(note)
    assert not any(LIST_NUMBER.fullmatch(p) for p in parts[:-1])


def test_sentences_cut_at_ends_and_clauses() -> None:
    assert sentences("The sum of a strand. An empty strand gives 0; nothing is refused.") == [
        "The sum of a strand.",
        "An empty strand gives 0;",
        "nothing is refused.",
    ]


def test_a_list_number_goes_with_its_item() -> None:
    assert sentences("Two steps. — 1. Parse it.") == ["Two steps.", "— 1. Parse it."]
    assert sentences("Two steps. — 1.") == ["Two steps.", "— 1."]


def test_an_empty_note_survives_ventilating() -> None:
    assert ventilated("dup\t; ") == "dup\t; "
    assert ventilated(";; ") == ";; "
