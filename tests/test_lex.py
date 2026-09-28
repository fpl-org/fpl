"""The pre-lexer keeps every code character's place in the source and every string's interior."""

from hypothesis import given
from hypothesis import strategies as st

from fpl.ast_surface import Text
from fpl.errors import FplError
from fpl.lex import PLACEHOLDER, Stashed, prelex
from fpl.parse import parse

PLAIN = st.text(alphabet="ab \t\n|[]“”「」⟦⟧;", max_size=30)


@given(PLAIN)
def test_every_code_character_comes_from_its_origin(source: str) -> None:
    try:
        lexed = prelex(source)
    except FplError:
        return
    assert len(lexed.origin) == len(lexed.code) + 1
    for char, at in zip(lexed.code, lexed.origin, strict=False):
        verbatim = at < len(source) and char == source[at]
        padded = char in " " + PLACEHOLDER and source[at] in "“「⟦"
        assert verbatim or padded or (char, at) == ("\n", len(source))


@given(st.text(alphabet=st.characters(exclude_characters="“”⟨"), max_size=20))
def test_a_string_keeps_its_interior(interior: str) -> None:
    item = parse(f"“{interior}”\n").lines[0].frames[0].cells[0].items[0]
    assert item == Text("str", (interior,) if interior else (), item.span)


def test_the_stash_holds_each_string_by_its_kind() -> None:
    assert prelex("“a” 「b」").stash == {0: Stashed("str", 1, 2, 0), 3: Stashed("raw", 5, 6, 0)}
