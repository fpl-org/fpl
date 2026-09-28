"""Printing is canonical: parse after print gives the tree back, and print after parse is
idempotent, on generated trees with blocks, on programs drawn from the grammar, and on the
corpus."""

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.extra.lark import from_lark
from test_ambiguity import FLAT

from fpl.ast_surface import Cell, Enclosure, Frame, Item, Line, Pair, Program, Text, Word
from fpl.errors import Span
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


def frames(items: st.SearchStrategy[Item]) -> st.SearchStrategy[tuple[Frame, ...]]:
    """One frame of cells, or several, where a frame beside a bar may be empty."""
    cell = st.lists(items, min_size=1, max_size=3).map(lambda xs: Cell(tuple(xs), AT))
    frame = st.lists(cell, min_size=1, max_size=3).map(lambda cs: Frame(tuple(cs), AT))
    beside = st.one_of(frame, st.just(Frame((), AT)))
    return st.one_of(frame.map(lambda f: (f,)), st.lists(beside, min_size=2, max_size=3).map(tuple))


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
    inner = frames(items(depth - 1))
    enclosures = st.builds(
        enclosure,
        st.sampled_from(PAIRS),
        st.one_of(st.just(()), inner),
    )
    islands = st.deferred(lambda: programs(depth - 1, 1))
    return st.one_of(words, enclosures, strings(islands))


def lines(depth: int, blocks: int) -> st.SearchStrategy[Line]:
    """A line and, while `blocks` allows, the lines of its block."""
    block = (
        st.lists(st.deferred(lambda: lines(depth, blocks - 1)), max_size=2)
        if blocks
        else st.just([])
    )
    return st.builds(line, frames(items(depth)), block)


def programs(depth: int, blocks: int) -> st.SearchStrategy[Program]:
    """Programs of up to three lines."""
    return st.lists(lines(depth, blocks), max_size=3).map(lambda ls: Program(tuple(ls), AT))


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
@given(programs(2, 2))
def test_print_then_parse_is_the_identity(program: Program) -> None:
    assert parse(render(program)) == program


@given(from_lark(FLAT, explicit={"TOKEN": TOKEN.map(lambda token: token + " ")}))
def test_print_is_idempotent_on_programs_derived_from_the_grammar(source: str) -> None:
    canonical(clean(source))


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
        ("\tk “a\n\tb⟨c⟩” 「r\n」\n", "k “a\nb⟨c⟩” 「r\n」\n"),
        ("", ""),
    ],
)
def test_the_canonical_layout(source: str, printed: str) -> None:
    assert render(parse(source)) == printed
