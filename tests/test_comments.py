"""A word's doc is the ;; lines above its head or opening its body; every other comment is
trivia, which changes no statement and no output."""

from dataclasses import replace

import pytest
from hypothesis import given
from hypothesis import strategies as st
from test_desugar import CURRY, core, outcome, programs

from fpl.ast_core import Define, Statement
from fpl.desugar import desugar, resugar
from fpl.driver import run
from fpl.parse import parse
from fpl.print import render

ABOVE = st.sampled_from(["", ";; d\n", ";;; s\n", ";;;; f\n"])
AFTER = st.sampled_from(["", " ; n", "\t⍝ n"])


@pytest.mark.parametrize(
    ("source", "printed"),
    [
        ("m/\n\t;; Sum.\n\tadd : x y -- z\n\t\t+\nm/add/doc\n", "“Sum.”\n"),
        ("m/\n\tadd : x y -- z\n\t\t;; Sum.\n\t\t+\n1 | 2 m/add | m/add/doc\n", "3 | “Sum.”\n"),
        (";; One.\n;; Two.\nf : -- y\n\t1\nf/doc\n", "“One.\nTwo.”\n"),
        ("f : -- y\n\t1\nf/doc\n", "“”\n"),
        (";; Old.\nf : -- y\n\t1\nf : -- y\n\t2\nf/doc\n", "“”\n"),
        ("f : -- y\n\t1\n\t;; Not a doc.\nf/doc\n", "“”\n"),
    ],
)
def test_a_words_doc_pushes_its_docstring(source: str, printed: str) -> None:
    """[D3.2] math/mean/doc pushes the docstring (draft3 examples/draft3.fpl:10): the ;; lines
    above the head, then those opening the body (draft2 examples/04-effects-holes-ascription
    .fpl:3), a line each; a word with none, or shadowed by one with none, pushes the empty
    string (holes doc-absent, doc-text)."""
    assert run(source) == printed


def undocumented(result: tuple[Statement, ...] | str) -> tuple[Statement, ...] | str:
    """Statements with every definition's doc blanked; an error's message as it is."""
    if isinstance(result, str):
        return result
    return tuple(replace(s, doc="") if isinstance(s, Define) else s for s in result)


@given(
    st.sampled_from(["", CURRY, "nop : --\n"]),
    programs,
    st.lists(st.tuples(ABOVE, AFTER), min_size=8, max_size=8),
)
def test_trivia_changes_no_statement_and_no_output(
    head: str, body: str, marks: list[tuple[str, str]]
) -> None:
    """Comments at all four levels, before and after every line, at its depth: the core is the
    same but for a definition's doc, and the program prints the same."""
    plain = (head + body).rstrip("\n").split("\n")
    commented = ""
    for line, (above, after) in zip(plain, marks * 2, strict=False):
        tabs = "\t" * (len(line) - len(line.lstrip("\t")))
        commented += f"{tabs}{above}{line}{after}\n"
    source = "\n".join(plain) + "\n"
    assert undocumented(core(commented)) == core(source)
    assert outcome(commented) == outcome(source)


@given(st.sampled_from(["", ";; a\n", ";; a\n;; b\n"]), st.sampled_from(["", "\t;; c\n"]))
def test_a_doc_is_written_back_as_it_desugars(above: str, opening: str) -> None:
    """Core written as source keeps each docstring as the ;; lines opening the body."""
    statements = desugar(parse(f"{above}f : -- y\n{opening}\t1\n"))
    assert desugar(parse(render(resugar(statements)))) == statements


def test_the_doc_of_a_definition_with_no_code_is_written_above_its_head() -> None:
    """Under a head with no body, a ;; looks past it to the next code line, so the doc of f
    would be read back as g's (tests/test_trivia.py); written above f's head, it stays f's."""
    statements = desugar(parse(";; First.\nf : --\ng : --\n"))
    assert desugar(parse(render(resugar(statements)))) == statements
