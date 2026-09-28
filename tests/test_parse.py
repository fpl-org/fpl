"""Parsing gives the surface AST or fails as one FplError inside the source, never otherwise."""

from collections.abc import Iterator
from typing import assert_never

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fpl.ast_surface import Cell, Comment, Enclosure, Frame, Item, Line, Program, Text, Word
from fpl.errors import FplError, Span
from fpl.lex import prelex
from fpl.parse import GRAMMAR, FplIndenter, parse, parser, placed, where, within

AT = Span(1, 1)
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


type Node = Program | Line | Comment | Frame | Cell | Item


def children(node: Node) -> tuple[Node, ...]:
    """The nodes directly inside a node, in order."""
    match node:
        case (
            Program(lines=inner) | Frame(cells=inner) | Cell(items=inner) | Enclosure(frames=inner)
        ):
            return inner
        case Line():
            return (*node.frames, *filter(None, (node.comment,)), *node.block)
        case Comment():
            return ()
        case Text():
            return tuple(part for part in node.parts if isinstance(part, Program))
        case Word():
            return ()
        case _:
            assert_never(node)


def spans(node: Node) -> Iterator[Span]:
    """Every span in a node, its own first, then its children's in order."""
    yield node.span
    for child in children(node):
        yield from spans(child)


@given(SOURCE)
def test_any_text_parses_or_fails_inside_it(source: str) -> None:
    error = failure(source)
    if error is not None:
        assert within(source, error.span.line, error.span.col)


@given(SOURCE)
def test_every_node_is_placed_inside_the_source(source: str) -> None:
    if failure(source) is None:
        assert all(within(source, at.line, at.col) for at in spans(parse(source)))


def test_an_empty_node_starts_where_its_enclosing_node_does() -> None:
    """HOLES.md empty-node-span."""
    program = parse("a |\n\t[ | ] ⟨⟩ 「r」\n")
    assert list(spans(program)) == [
        *(Span(1, 1),) * 6,
        *(Span(2, 2),) * 6,
        *(Span(2, 8),) * 2,
        Span(2, 11),
    ]


def test_within_names_a_character_or_the_end_of_a_line() -> None:
    assert within("ab", 1, 3)
    assert not within("ab", 1, 4)
    assert not within("ab", 2, 1)


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
        ("a ;; d\n", "ERROR: 1:3 a ;; comment stands on a line of its own"),
        ("a | ;;; s\n", "ERROR: 1:5 a ;;; comment stands on a line of its own"),
        ("[ a ; c\n b ]\n", "ERROR: 1:5 a comment cannot stand inside an enclosure"),
        ("a\n[ a )\n", "ERROR: 2:5 ) does not close ["),
        ("a\n\t b\n", "ERROR: 2:2 indentation must be tabs"),
        ("a\n\t\t[\n\tb ]\n", "ERROR: 3:2 dedent below line 2, but its [ is still open"),
        ("a\n\t[ b\n", "ERROR: 2:2 [ never closed"),
    ],
)
def test_a_refusal_is_one_error_line(source: str, expected: str) -> None:
    assert str(failure(source)) == expected


def test_lines_frames_cells_and_blocks() -> None:
    program = parse("a | b\tc\n\td ;x\n")
    here = Span(1, 1)
    cells = (Cell((word("b"),), here), Cell((word("c"),), here))
    first = Line(
        (Frame((Cell((word("a"),), here),), here), Frame(cells, here)),
        (Line(line((word("d"),)).frames, (), here, Comment(1, (";x",), here)),),
        here,
    )
    assert program == Program((first,), here)


@pytest.mark.parametrize("glued", ["a", "X"])
def test_a_string_glued_to_a_word_is_an_item_of_its_own(glued: str) -> None:
    items = parse(glued + "“x”\n").lines[0].frames[0].cells[0].items
    assert items == (word(glued), Text("str", ("x",), Span(1, 2)))


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
    assert shown == [("quotation", 2), ("prefix", 1), ("group", 1), ("dict", 1)]


@pytest.mark.parametrize("source", ["[]", "⟨⟩", "()", "{}", "[\t]", "[\n]"])
def test_an_empty_enclosure_holds_one_empty_frame(source: str) -> None:
    """PSJ 2026-09-29: an enclosure holds bars + 1 frames; [ | ] holds two."""
    (item,) = parse(source + "\n").lines[0].frames[0].cells[0].items
    assert isinstance(item, Enclosure)
    assert item.frames == (Frame((), AT),)


@pytest.mark.parametrize("source", ["", "\n", "\n\n\n"])
def test_a_blank_source_is_one_empty_line(source: str) -> None:
    assert parse(source) == Program((Line((Frame((), AT),), (), AT),), AT)


def test_only_the_first_line_is_empty_and_it_may_hold_a_block() -> None:
    empty = Line((Frame((), AT),), (line((word("x"),)),), AT)
    assert parse("\n\tx\n\ny\n") == Program((empty, line((word("y"),))), AT)


def test_a_comment_is_held_by_its_line() -> None:
    program = parse("a ; x\n; y\n;; d\n\t⍝ g\nb\n")
    note = Comment(1, ("; x", "; y"), Span(1, 3))
    doc = Comment(2, (";; d",), Span(3, 1))
    glyph = Line((Frame((), AT),), (), AT, Comment(1, ("⍝ g",), AT))
    assert program.lines == (
        Line(line((word("a"),)).frames, (), AT, note),
        Line((), (glyph,), AT, doc),
        line((word("b"),)),
    )
    assert [line.comment and line.comment.span for line in program.lines] == [
        Span(1, 3),
        Span(3, 1),
        None,
    ]


def test_a_string_is_read_with_its_islands_and_without_incidental_indentation() -> None:
    program = parse("a\n\tx “p\n\t\tq ⟨c⟩ r” 「⟨raw⟩\n\t」\n")
    text, raw = program.lines[0].block[0].frames[0].cells[0].items[1:]
    island = Program((line((word("c"),)),), Span(1, 1))
    assert text == Text("str", ("p\n\tq ", island, " r"), Span(1, 1))
    assert raw == Text("raw", ("⟨raw⟩\n\t",), Span(1, 1))
    assert isinstance(text, Text)
    assert isinstance(text.parts[1], Program)
    assert text.parts[1].lines[0].span == Span(3, 6)


def test_the_indentation_a_string_drops_is_of_the_line_it_opens_on() -> None:
    program = parse("a\nb\n\tx “p\n\tq”\n")
    assert program.lines[1].block[0].frames[0].cells[0].items[1] == Text("str", ("p\nq",), AT)


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
