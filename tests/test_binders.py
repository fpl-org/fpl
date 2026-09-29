"""Names and values: →x binds, #name symbols, { } dicts (draft2 §scope follows the tree,
§objects are directories; decision f; server example)."""

import pytest

from fpl.driver import run
from fpl.errors import FplError


@pytest.mark.parametrize(
    ("source", "printed"),
    [
        ("1 →x | 2 →x | x\n", "2\n"),
        ("1 ->x | x\n", "1\n"),
        ("2 →k | [ k times ]\n", "[ 2 times ]\n"),
        ("1 →x | [ 2 →x x ] | x\n", "[ 2 →x x ] 1\n"),
        ("1 →x | [ 2 →y x y ]\n", "[ 2 →y 1 y ]\n"),
        ("1 →x | ⟨ [ x ] ⟩\n", "⟨ [ 1 ] ⟩\n"),
        ("1 →x\n", ""),
        ("→x\n", "[ →x ]\n"),
        ("1 2 →x | x x +\n", "2 4\n"),
    ],
)
def test_a_binder_names_the_top_for_the_rest_of_its_line(source: str, printed: str) -> None:
    """Decision f: →x takes the top and names it; a later binder shadows, the name inside a
    quotation is the value it named, a binder alone on an empty stack is a section."""
    assert run(source) == printed


def test_a_binder_in_a_body_reaches_the_lines_after_it_and_their_children() -> None:
    """draft2 examples/07-scope-follows-the.fpl:3-5 and server.fpl:3-4: a name bound on a
    line of a body is read on the lines below it, and in the blocks under them."""
    source = "f : x -- y\n\t→x\n\tx x +\ng : x -- q\n\t→x\n\t[ ] ,\n\t\tx 1 +\n3 f\n2 g\n"
    assert run(source) == "6\n[ 2 | 1 + ]\n"


@pytest.mark.parametrize("source", ["1 →x\nx\n", "[ 1 →x ] x\n", "→x | x\n", "1 →a/b\n"])
def test_a_name_dies_with_the_line_or_quotation_that_bound_it(source: str) -> None:
    """Decision f: a binder is mortal; past its scope the name is no word at all."""
    with pytest.raises(FplError) as caught:
        run(source)
    assert str(caught.value) == "ERROR: 1:1 no evaluator yet"


@pytest.mark.parametrize(
    ("source", "printed"),
    [
        ("#x\n", "#x\n"),
        ("#x #y swap\n", "#y #x\n"),
        ("#x →s | s\n", "#x\n"),
        ("{ sep “ ” end 1 }\n", "{ sep “ ” end 1 }\n"),
        ("g : -- y\n\t3\n{ a g b #c }\n", "{ a 3 b #c }\n"),
        ("1 →x | { a x }\n", "{ a 1 }\n"),
        ("{}\n", "{}\n"),
    ],
)
def test_symbols_and_dicts_are_values(source: str, printed: str) -> None:
    """draft2 examples/08-objects-are-directories.fpl:3 (#x #y swap: symbols do not strand);
    match examples/06-6-python-s-keywords.fpl:4 ({ sep “, ” }: literal keys, values run)."""
    assert run(source) == printed


@pytest.mark.parametrize(
    ("source", "error"),
    [
        ("{ a 1 a 2 }\n", "ERROR: 1:7 repeated key a"),
        ("g : -- y\ng →x\n", "ERROR: 2:3 stack underflow"),
        ("g : -- y\n{ a g }\n", "ERROR: 2:1 a dict value is one value"),
    ],
)
def test_binders_and_dicts_refuse_at_their_position(source: str, error: str) -> None:
    """fpl/fon.py dict: a key given twice is refused where it repeats."""
    with pytest.raises(FplError) as caught:
        run(source)
    assert str(caught.value) == error


@pytest.mark.parametrize(
    "source", ["#x\u00b4\n", "#a/b\n", "{ a }\n", "{ 1 2 }\n", "{ a + }\n", "{ a (+ 1 2) }\n"]
)
def test_what_binders_do_not_yet_read_is_refused(source: str) -> None:
    with pytest.raises(FplError) as caught:
        run(source)
    assert str(caught.value) == "ERROR: 1:1 no evaluator yet"
