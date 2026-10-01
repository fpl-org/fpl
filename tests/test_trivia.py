"""Comments attach by level: a note to its line, ;; to the next code line, ;;; and ;;;; to the
file."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fpl.parse import parse
from fpl.trivia import Attached, Attachment, comments

LINES = {"code": "a b", "trailing": "a ; t", "doc": ";; t", "section": ";;; t", "file": ";;;; t"}
LEVELS = {"trailing": 1, "doc": 2, "section": 3, "file": 4}
KINDS: dict[str, Attachment] = {
    "trailing": "trailing",
    "doc": "doc",
    "section": "section",
    "file": "file",
}


@given(st.lists(st.sampled_from(sorted(LINES)), min_size=1, max_size=12))
def test_a_comment_attaches_by_its_level(kinds: list[str]) -> None:
    code = [n for n, kind in enumerate(kinds, 1) if kind in {"code", "trailing"}]
    expected = [
        Attached(
            n,
            LEVELS[kind],
            KINDS[kind],
            n
            if kind == "trailing"
            else next((k for k in code if k > n), None)
            if kind == "doc"
            else None,
            "t",
        )
        for n, kind in enumerate(kinds, 1)
        if kind != "code"
    ]
    assert list(comments(parse("\n".join(LINES[kind] for kind in kinds) + "\n"))) == expected


def test_a_doc_belongs_to_the_line_after_it_and_a_string_holds_none() -> None:
    source = ";; above\nf : x\n\t;; under\n\tx “; no”\n\t;;; inner\n"
    assert comments(parse(source)) == (
        Attached(1, 2, "doc", 2, "above"),
        Attached(3, 2, "doc", 4, "under"),
        Attached(5, 3, "section", None, "inner"),
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("a\n\t;; x\n\t;; y\n\tb\n", [(2, "doc", 4), (3, "doc", 4)]),
        ("f: x\n\n\t;; d\n", [(3, "doc", None)]),
        ("f: x\n;; d\ng\n", [(2, "doc", 3)]),
        ("a ; x\n; y\n", [(1, "trailing", 1)]),
    ],
)
def test_a_comment_looks_past_comments_and_blanks_for_its_code(
    source: str, expected: list[tuple[int, Attachment, int]]
) -> None:
    """A doc looks past comment lines to the next code line; a note continues over its lines."""
    assert [(c.line, c.kind, c.target) for c in comments(parse(source))] == expected


def test_a_note_reads_as_its_lines_joined_without_their_marks() -> None:
    assert comments(parse("a ;X one\n;two\n⍝⍝ three\n")) == (
        Attached(1, 1, "trailing", 1, "X one two three"),
    )
