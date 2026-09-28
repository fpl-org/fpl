"""Comments attach by level: trailing to their line, ;; to the next line or a head, ;;; and ;;;;
to the file."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fpl.trivia import Attachment, Comment, comments

KINDS: dict[str, Attachment] = {
    "trailing": "trailing",
    "before": "before",
    "section": "section",
    "file": "file",
}
LINES = {"code": "a b", "trailing": "a ; t", "before": ";; t", "section": ";;; t", "file": ";;;; t"}


@given(st.lists(st.sampled_from(sorted(LINES)), max_size=12))
def test_a_comment_attaches_by_its_level(kinds: list[str]) -> None:
    code = [n for n, kind in enumerate(kinds, 1) if kind in {"code", "trailing"}]
    expected = [
        Comment(
            n,
            {"trailing": 1, "before": 2, "section": 3, "file": 4}[kind],
            KINDS[kind],
            n
            if kind == "trailing"
            else next((k for k in code if k > n), None)
            if kind == "before"
            else None,
            "t",
        )
        for n, kind in enumerate(kinds, 1)
        if kind != "code"
    ]
    assert list(comments("\n".join(LINES[kind] for kind in kinds) + "\n")) == expected


def test_a_comment_by_a_head_is_its_doc_and_a_string_holds_none() -> None:
    source = ";; above\nf : x\n\t;; under\n\tx “; no”\n\t;;; inner\n"
    assert comments(source) == (
        Comment(1, 2, "doc", 2, "above"),
        Comment(3, 2, "doc", 2, "under"),
        Comment(5, 3, "before", None, "inner"),
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("a\n\t;; x\n\t;; y\n\tb\n", [(2, "before", 4), (3, "before", 4)]),
        ("f: x\n\n\t;; d\n", [(3, "doc", 1)]),
        ("f: x\n;; d\ng\n", [(2, "before", 3)]),
    ],
)
def test_a_comment_looks_past_comments_and_blanks_for_its_code(
    source: str, expected: list[tuple[int, Attachment, int]]
) -> None:
    """An indented comment is not code; a doc sits deeper than the head above it."""
    assert [(c.line, c.kind, c.target) for c in comments(source)] == expected
