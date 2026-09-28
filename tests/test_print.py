"""Printing is canonical: parse after print gives the tree back, and print after parse is
idempotent, on generated trees with blocks, on programs drawn from the grammar, and on the
corpus."""

from pathlib import Path

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st
from hypothesis.extra.lark import from_lark
from test_ambiguity import FLAT

from fpl.ast_surface import Cell, Comment, Enclosure, Frame, Item, Line, Pair, Program, Text, Word
from fpl.errors import FplError, Span
from fpl.lex import MODS, shape
from fpl.parse import parse
from fpl.print import render

AT = Span(1, 1)
CORPUS = sorted(Path(__file__).parent.parent.glob("features/*/examples/*.fpl"))
PLAIN = r"\s\[\]()“”「」⟦⟧⟨⟩{}|⍝;¶"
TOKEN = st.from_regex(rf"[^{PLAIN}{MODS}]+[{MODS}]*|[{MODS}]+", fullmatch=True)
PAIRS: tuple[Pair, ...] = ("quotation", "prefix", "group", "dict")


def word(token: str) -> Word:
    """The word a token reads as."""
    read = shape(token)
    assert read is not None
    return Word(*read, AT)


def strings(programs: st.SearchStrategy[Program]) -> st.SearchStrategy[Text]:
    """Raw strings, and interpolating ones of text and islands, as the parser gives them: text
    parts non-empty and never two in a row, no bracket or quote a reader would count."""
    raw = st.text(alphabet=st.characters(exclude_characters="「」“”⟨⟩"), max_size=8)
    plain = st.text(alphabet=st.characters(exclude_characters="“”⟨⟩"), max_size=8)

    def joined(texts: list[str], islands: list[Program]) -> Text:
        parts: list[str | Program] = [texts[0]]
        for island, after in zip(islands, texts[1:], strict=False):
            parts += [island, after]
        return Text("str", tuple(part for part in parts if part != ""), AT)

    interpolated = st.lists(programs, max_size=2).flatmap(
        lambda islands: st.lists(plain, min_size=len(islands) + 1, max_size=len(islands) + 1).map(
            lambda texts: joined(texts, islands)
        )
    )
    return st.one_of(raw.map(lambda r: Text("raw", (r,), AT)), interpolated)


def frames(
    items: st.SearchStrategy[Item], alone: bool = False
) -> st.SearchStrategy[tuple[Frame, ...]]:
    """One frame of cells, or several, where a frame beside a bar may be empty; `alone`, a lone
    empty frame too, as in an enclosure."""
    cell = st.lists(items, min_size=1, max_size=3).map(lambda xs: Cell(tuple(xs), AT))
    frame = st.lists(cell, min_size=1, max_size=3).map(lambda cs: Frame(tuple(cs), AT))
    beside = st.one_of(frame, st.just(Frame((), AT)))
    if alone:
        return st.lists(beside, min_size=1, max_size=3).map(tuple)
    return st.one_of(frame.map(lambda f: (f,)), st.lists(beside, min_size=2, max_size=3).map(tuple))


TEXT = st.text(alphabet=st.characters(exclude_characters="\n\r"), max_size=6)


def note(mark: str, texts: list[str]) -> Comment:
    """A note of one or more lines."""
    return Comment(1, tuple(mark + text for text in texts), AT)


def doc(level: int, text: str) -> Comment:
    """A ;; ;;; or ;;;; comment on a line of its own."""
    return Comment(level, (";" * level + " " + text,), AT)


def noted(code: Line, comment: Comment) -> Line:
    """A code line carrying a note."""
    return Line(code.frames, code.block, AT, comment)


def own(block: list[Line], comment: Comment) -> Line:
    """A comment on a line of its own, heading a block."""
    return Line((), tuple(block), AT, comment)


def opened(block: list[Line]) -> Line:
    """The empty first line of a program that opens blank."""
    return Line((Frame((), AT),), tuple(block), AT)


def first(pair: tuple[Line, list[Line]]) -> list[Line]:
    """A first line before the rest."""
    return [pair[0], *pair[1]]


NOTES = st.builds(note, st.sampled_from(["; ", "⍝"]), st.lists(TEXT, min_size=1, max_size=3))
DOCS = st.builds(doc, st.integers(2, 4), TEXT)


def enclosure(pair: Pair, body: tuple[Frame, ...]) -> Enclosure:
    """An enclosure placed nowhere in particular."""
    return Enclosure(pair, body, AT)


def line(frames_: tuple[Frame, ...], block: list[Line]) -> Line:
    """A line placed nowhere in particular."""
    return Line(frames_, tuple(block), AT)


def items(depth: int) -> st.SearchStrategy[Item]:
    """Words, strings and enclosures nested `depth` deep."""
    words = TOKEN.map(word)
    if depth == 0:
        return words
    enclosures = st.builds(enclosure, st.sampled_from(PAIRS), frames(items(depth - 1), alone=True))
    islands = st.deferred(lambda: programs(depth - 1, 1))
    return st.one_of(words, enclosures, strings(islands))


def lines(depth: int, blocks: int, comments: bool = False) -> st.SearchStrategy[Line]:
    """A line and, while `blocks` allows, the lines of its block; with `comments`, a line may
    carry a note, or be a ;; comment of its own."""
    block = (
        st.lists(st.deferred(lambda: lines(depth, blocks - 1, comments)), max_size=2)
        if blocks
        else st.just([])
    )
    code = st.builds(line, frames(items(depth)), block)
    if not comments:
        return code
    return st.one_of(code, st.builds(noted, code, NOTES), st.builds(own, block, DOCS))


def programs(depth: int, blocks: int, top: bool = False) -> st.SearchStrategy[Program]:
    """Programs of one to three lines; at the top, with comments, and the first line may be
    empty (an island's lines are not searched for comments here)."""
    body = st.lists(lines(depth, blocks, top), min_size=1, max_size=3)
    if top:
        empty = st.lists(lines(depth, 0, top), max_size=2).map(opened)
        rest = st.lists(lines(depth, blocks, top), max_size=2)
        body = st.one_of(body, st.tuples(empty, rest).map(first))
    return body.map(lambda ls: Program(tuple(ls), AT))


def clean(source: str) -> str:
    """A flat draw as a program: no line opens with a tab or a space, and no line is blank,
    since the flat grammar has no blocks to indent. Each drawn token ends in a space, which
    the grammar ignores, so that two tokens drawn in a row stay two."""
    kept = (line.strip(" \t\f") for line in source.split("\n"))
    return "".join(line + "\n" for line in kept if line)


def canonical(source: str) -> None:
    """render∘parse is idempotent on source, and parse∘render the identity on its tree."""
    tree = parse(render(parse(source)))
    out = render(tree)
    assert render(parse(out)) == out
    assert parse(out) == tree


@pytest.mark.obligation("print then parse is the identity")
@given(programs(2, 2, top=True))
def test_print_then_parse_is_the_identity(program: Program) -> None:
    assert parse(render(program)) == program


@given(from_lark(FLAT, explicit={"TOKEN": TOKEN.map(lambda token: token + " ")}))
def test_print_is_idempotent_on_programs_derived_from_the_grammar(source: str) -> None:
    try:
        parse(clean(source))
    except FplError as refused:  # a draw may set ;; after code, which the builder refuses
        assume("stands on a line of its own" not in str(refused))
        raise
    canonical(clean(source))


@given(st.text(alphabet="\t \f", max_size=6))
def test_a_blank_line_is_part_of_its_blank_run_whatever_it_holds(blank: str) -> None:
    """Tabs, spaces and form feeds (a page separator) on a line between two lines leave no
    line behind, so the source prints without it; a space right after the tabs that open a
    line is refused, as on any line (tests/test_parse.py)."""
    assume(not blank.lstrip("\t").startswith(" "))
    assert render(parse(f"a\n\tx\n{blank}\n\ty\n")) == "a\n\tx\n\ty\n"


@pytest.mark.parametrize("program", CORPUS, ids=[p.stem for p in CORPUS])
def test_print_keeps_the_tree_of_the_corpus(program: Path) -> None:
    source = program.read_text()
    assert parse(render(parse(source))) == parse(source)
    canonical(source)


@pytest.mark.parametrize(
    ("source", "printed"),
    [
        ("a\t\tb|c  [ d |e ]( )\n\tx\n", "a\tb | c [ d | e ] ()\n\tx\n"),
        ("f\n\tg\n\t\th ⟨⟩\n", "f\n\tg\n\t\th ⟨⟩\n"),
        ("|x\na|\na||b\n[ | ]\n", "| x\na |\na | | b\n[ | ]\n"),
        ("[\t]\n", "[]\n"),
        ("[] ⟨ | ⟩\n", "[] ⟨ | ⟩\n"),
        ("\n\n\tx\n", "\n\tx\n"),
        ("\n", ""),
        ("| ; x\n", "|\t; x\n"),
        ("a\n\f\nb\n", "a\nb\n"),
        ("a\n\f \nb\n", "a\nb\n"),
        ("a\n\t\f\nb\n", "a\nb\n"),
        ("a;x\n;y\n\tb | c ⍝ g\n", "a\t;x\n\t;y\n\tb | c\t⍝ g\n"),
        ("\ta\tb ; n\n\t\t\t; m\n", "a\tb\t; n\n\t\t; m\n"),
        (";;;; f\n;;; s\n\n;; d\nf ; t\n", ";;;; f\n;;; s\n;; d\nf\t; t\n"),
        ("\tk “a\n\tb⟨c⟩” 「r\n」\n", "k “a\nb⟨c⟩” 「r\n」\n"),
        ("a\n\tx “p\n\tq”\n", "a\n\tx “p\n\tq”\n"),
        ("X “a\nb”\n", "X “a\nb”\n"),
        ("a\n\tx “p\n\ty” “u\n\tv”\n", "a\n\tx “p\n\ty” “u\n\tv”\n"),
        ("“a\n b” “p\nq”\n", "“a\n b” “p\nq”\n"),
        ("“a\n\tb\nc” “p\nq”\n", "“a\n\tb\nc” “p\nq”\n"),
        ("", ""),
    ],
)
def test_the_canonical_layout(source: str, printed: str) -> None:
    assert render(parse(source)) == printed
