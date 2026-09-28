"""Parsing gives the surface AST or fails as one FplError inside the source, never otherwise."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fpl.ast_surface import Cell, Enclosure, Frame, Line, Program, Text, Word
from fpl.errors import FplError, Span
from fpl.lex import prelex
from fpl.parse import GRAMMAR, FplIndenter, parse, parser, placed, where, within

SOURCE = st.text(alphabet="ab1 \t\n|;⍝“”「」⟦⟧⟨⟩[](){}¶\u00b4→$#/.\r\f", max_size=40)


def failure(source: str) -> FplError | None:
    """The error parsing gives, or None when it parses."""
    try:
        parse(source)
    except FplError as error:
        return error
    return None


def word(text: str) -> Word:
    """A plain name."""
    return Word("", "name", (text,), "", Span(1, 1))


def line(*frames: tuple[Word | Text | Enclosure, ...], block: tuple[Line, ...] = ()) -> Line:
    """A line of one-cell frames."""
    here = Span(1, 1)
    return Line(tuple(Frame((Cell(items, here),), here) for items in frames), block, here)


@given(SOURCE)
def test_any_text_parses_or_fails_inside_it(source: str) -> None:
    error = failure(source)
    if error is not None:
        assert within(source, error.span.line, error.span.col)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("“a 「b” c」\n", "ERROR: 1:9 」 closes nothing"),
        ("[ 1 2\n", "ERROR: 1:1 [ never closed"),
        ("a\n\t\tb\n\tc\n", "ERROR: 3:2 dedent to a level never opened"),
        ("a\n  b\n", "ERROR: 2:1 indentation must be tabs"),
        ("\ta [\nb ]\n", "ERROR: 2:1 dedent below line 1, but its [ is still open"),
        ("x “ab\n", "ERROR: 1:3 “ never closed"),
        ("a ]\n", "ERROR: 1:3 ] closes nothing"),
        ("[ a )\n", "ERROR: 1:5 ) does not close ["),
        ("“⟨a” b\n", "ERROR: 1:2 ⟨ never closed"),
        ("a\u00b4b\n", "ERROR: 1:1 a modifier ends its word: a\u00b4b"),
        ("“s”\n| ⟧\n", "ERROR: 2:3 ⟧ closes nothing"),
        ("a\x0b\n", "ERROR: 1:2 unexpected input"),
        ("[\n]\t]", "ERROR: 2:3 ] closes nothing"),
        ("a\n]", "ERROR: 2:1 ] closes nothing"),
        ("\n\tx\n", "ERROR: 1:1 unexpected input"),
    ],
)
def test_a_refusal_is_one_error_line(source: str, expected: str) -> None:
    assert str(failure(source)) == expected


def test_lines_frames_cells_and_blocks() -> None:
    program = parse("a | b\tc\n\td ;x\n")
    here = Span(1, 1)
    cells = (Cell((word("b"),), here), Cell((word("c"),), here))
    first = Line(
        (Frame((Cell((word("a"),), here),), here), Frame(cells, here)), (line((word("d"),)),), here
    )
    assert program == Program((first,), here)


def test_a_string_glued_to_a_word_is_an_item_of_its_own() -> None:
    items = parse("a“x”\n").lines[0].frames[0].cells[0].items
    assert items == (word("a"), Text("str", ("x",), Span(1, 2)))


def test_every_node_starts_where_it_is_written() -> None:
    program = parse("x\n⟦c⟧ “a\nb” [ y ]\n")
    items = program.lines[1].frames[0].cells[0].items
    assert [item.span for item in items] == [Span(2, 5), Span(3, 4)]
    assert isinstance(items[1], Enclosure)
    assert items[1].frames[0].cells[0].items[0].span == Span(3, 6)


def test_enclosures_hold_frames() -> None:
    program = parse("[ a | b ] (a) ⟨⟩ {a\n\tb}\n")
    shown = [
        (item.pair, len(item.frames))
        for item in program.lines[0].frames[0].cells[0].items
        if isinstance(item, Enclosure)
    ]
    assert shown == [("quotation", 2), ("prefix", 1), ("group", 0), ("dict", 1)]


def test_a_string_is_read_with_its_islands_and_without_incidental_indentation() -> None:
    program = parse("a\n\tx “p\n\t\tq ⟨c⟩ r” 「⟨raw⟩\n\t」\n")
    text, raw = program.lines[0].block[0].frames[0].cells[0].items[1:]
    island = Program((line((word("c"),)),), Span(1, 1))
    assert text == Text("str", ("p\n\tq ", island, " r"), Span(1, 1))
    assert raw == Text("raw", ("⟨raw⟩\n\t",), Span(1, 1))
    assert isinstance(text, Text)
    assert isinstance(text.parts[1], Program)
    assert text.parts[1].lines[0].span == Span(3, 6)


def test_a_block_comment_leaves_no_indentation_and_separates_words() -> None:
    assert parse("⟦ c ⟧   a⟦ d ⟧b\n") == Program((line((word("a"), word("b"))),), Span(1, 1))


@pytest.mark.parametrize(
    ("token", "shape"),
    [
        ("->k", ("->", "name", ("k",), "")),
        ("→k", ("→", "name", ("k",), "")),
        ("$cell", ("$", "name", ("cell",), "")),
        ("../io", ("../", "name", ("io",), "")),
        ("math/mean/doc", ("", "path", ("math", "mean", "doc"), "")),
        ("+\u00b4", ("", "name", ("+",), "\u00b4")),
        ("draw¨", ("", "name", ("draw",), "¨")),
        ("rect⁼", ("", "name", ("rect",), "⁼")),
        ("word?", ("", "name", ("word?",), "")),
        ("set!", ("", "name", ("set!",), "")),
        ("a-b", ("", "name", ("a-b",), "")),
        ("1+2", ("", "name", ("1+2",), "")),
        ("2", ("", "number", ("2",), "")),
        ("-2.5", ("", "number", ("-2.5",), "")),
        ("∞", ("", "number", ("∞",), "")),
        ("../store/new", ("../", "path", ("store", "new"), "")),
        ("shape/kind", ("", "path", ("shape", "kind"), "")),
        ("#sym", ("#", "name", ("sym",), "")),
        ("&h", ("&", "name", ("h",), "")),
        ("..", ("..", "modifier", ("",), "")),
        ("˙", ("", "modifier", ("",), "˙")),
    ],
)
def test_the_affix_pass_reads_token_shape(
    token: str, shape: tuple[str, str, tuple[str, ...], str]
) -> None:
    item = parse(token + "\n").lines[0].frames[0].cells[0].items[0]
    assert isinstance(item, Word)
    assert (item.prefix, item.kind, item.body, item.mods) == shape


@pytest.mark.parametrize("opener", ["[", "“⟨", "\t"])
def test_nesting_too_deep_to_read_is_refused(opener: str) -> None:
    """HOLES.md nesting-depth: past the depth the build can recurse to, one error, no traceback."""
    closer = {"[": "]", "“⟨": "⟩”", "\t": ""}[opener]
    source = "a\n" + "".join("\t" * k + "a\n" for k in range(1, 1000))
    if closer:
        source = opener * 1000 + closer * 1000 + "\n"
    assert str(failure(source)) == "ERROR: 1:1 nesting too deep to read"


def test_a_failure_lark_cannot_place_is_at_the_end_of_the_source() -> None:
    assert placed("ab\nc", prelex("ab\nc"), None) == Span(2, 2) == where("ab\nc", -1, -1)


def test_a_block_comment_opening_a_line_keeps_its_tabs() -> None:
    """HOLES.md block-comment-at-line-start: the comment and the spaces after it go, tabs stay."""
    assert parse("a\n\t⟦c⟧ b\n") == parse("a\n\tb\n")


def test_the_indenter_reads_terminals_the_grammar_makes() -> None:
    """One tab per level, over terminals the grammar makes or declares: a renamed terminal would
    leave the indenter counting nothing."""
    made = {terminal.name for terminal in parser().terminals}
    indenter = FplIndenter()
    brackets = [*indenter.OPEN_PAREN_types, *indenter.CLOSE_PAREN_types]
    assert {indenter.NL_type, *brackets} <= made
    declared = f"%declare {indenter.INDENT_type} {indenter.DEDENT_type}"
    assert declared in GRAMMAR.read_text()
    assert indenter.tab_len == 1
