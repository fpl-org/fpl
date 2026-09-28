"""Comments attach by level: trailing to their line, ;; to the next line or a head, ;;; and ;;;;
to the file."""

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
