"""Comments attach by level: a note to its line; ;; to the next code line, or as a doc to the
definition head it stands above or opens the body of; ;;; and ;;;; to the file."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fpl.parse import parse
from fpl.trivia import Attached, Attachment, comments, docstrings, head

LINES = {
    "code": "a b",
    "head": "f : x -- y",
    "trailing": "a ; t",
    "doc": ";; t",
    "section": ";;; t",
    "file": ";;;; t",
}
CODE = {"code", "head", "trailing"}


def attached(kinds: list[str], n: int) -> Attached:
    """What the comment on line n attaches to, among lines of the given kinds, none indented."""
    kind = kinds[n - 1]
    after = next((k for k in range(n + 1, len(kinds) + 1) if kinds[k - 1] in CODE), None)
    if kind == "trailing":
        return Attached(n, 1, "trailing", n, "t")
    if kind == "doc":
        head: Attachment = "doc" if after and kinds[after - 1] == "head" else "before"
        return Attached(n, 2, head, after, "t")
    level: Attachment = "section" if kind == "section" else "file"
    return Attached(n, 3 if kind == "section" else 4, level, None, "t")


@given(st.lists(st.sampled_from(sorted(LINES)), min_size=1, max_size=12))
def test_a_comment_attaches_by_its_level(kinds: list[str]) -> None:
    """Any run of unindented lines: each comment attaches as its level and the next code line
    decide, which attached() works out independently."""
    comment = [n for n, kind in enumerate(kinds, 1) if kind not in {"code", "head"}]
    expected = [attached(kinds, n) for n in comment]
    assert list(comments(parse("\n".join(LINES[kind] for kind in kinds) + "\n"))) == expected


def test_a_doc_belongs_to_the_head_above_or_around_it_and_a_string_holds_none() -> None:
    """A ;; above a head and one opening its body are both its docs, a ;;; in the body is a
    section, and a ; inside a string is no comment."""
    source = ";; above\nf : x\n\t;; under\n\tx “; no”\n\t;;; inner\n"
    assert comments(parse(source)) == (
        Attached(1, 2, "doc", 2, "above"),
        Attached(3, 2, "doc", 2, "under"),
        Attached(5, 3, "section", None, "inner"),
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("a\n\t;; x\n\t;; y\n\tb\n", [(2, "before", 4), (3, "before", 4)]),
        ("f: x\n\n\t;; d\n", [(3, "before", None)]),
        ("f: x\n;; d\ng\n", [(2, "before", 3)]),
        ("a ; x\n; y\n", [(1, "trailing", 1)]),
        ("f : -- y\n\t;; d\n\t;; e\n\t1\n", [(2, "doc", 1), (3, "doc", 1)]),
        ("f : -- y\n\t;; d\n\tg : -- z\n\t\t1\n", [(2, "doc", 3)]),
        ("f : -- y\n\t1\n\t;; d\n", [(3, "before", None)]),
        ("f : -- y\n\t1\n\t;; d\ng\n", [(3, "before", 4)]),
    ],
)
def test_a_comment_looks_past_comments_and_blanks_for_its_code(
    source: str, expected: list[tuple[int, Attachment, int]]
) -> None:
    """A ;; looks past comment lines to the next code line, and is a doc when that line is a
    head, or when it opens a head's body (SHAR gram/test_fpl.py comments()); a note continues
    over its lines."""
    assert [(c.line, c.kind, c.target) for c in comments(parse(source))] == expected


def test_a_note_reads_as_its_lines_joined_without_their_marks() -> None:
    """A note running over lines, ; or ⍝ marks of any count, reads as one text attached to
    the code line it trails."""
    assert comments(parse("a ;X one\n;two\n⍝⍝ three\n")) == (
        Attached(1, 1, "trailing", 1, "X one two three"),
    )


def test_a_docstring_is_its_docs_a_line_each() -> None:
    """The ;; lines above a head, then those opening its body, one line each."""
    source = ";; a\n;; b\nf : -- y\n\t;; c\n\t1\ng : -- y\n\t2\n"
    assert docstrings(parse(source)) == {3: "a\nb\nc"}


def test_a_line_with_no_frames_is_no_head() -> None:
    """A ;; line holds no frames, so it has no first cell to read a `:` from."""
    assert not head(parse(";; f : x -- y\n").lines[0])
