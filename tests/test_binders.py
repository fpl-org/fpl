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
        ("1 →x | dup\n", "[ dup ]\n"),
    ],
)
def test_a_binder_names_the_top_for_the_rest_of_its_line(source: str, printed: str) -> None:
    """Decision f: →x takes the top and names it; a later binder shadows, the name inside a
    quotation is the value it named, a binder alone on an empty stack is a section; a binder
    leaves nothing, so a frame after it that takes the value it took is a section."""
    assert run(source) == printed


def test_a_binder_in_a_body_reaches_the_lines_after_it_and_their_children() -> None:
    """draft2 examples/07-scope-follows-the.fpl:3-5 and server.fpl:3-4: a name bound on a
    line of a body is read on the lines below it, and in the blocks under them."""
    source = "f : x -- y\n\t→x\n\tx x +\ng : x -- q\n\t→x\n\t[ ] ,\n\t\tx 1 +\n3 f\n2 g\n"
    assert run(source) == "6\n[ 2 | 1 + ]\n"


@pytest.mark.parametrize("source", ["1 →x\nx\n", "[ 1 →x ] x\n", "→x | x\n", "1 →a/b\na/b\n"])
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
        ("g : -- y\n\t[ ] !\ng →x\n", "ERROR: 3:3 stack underflow"),
        ("g : -- y\n\t[ ] !\n{ a g }\n", "ERROR: 3:1 a dict value is one value"),
        ("g : -- y\n\t[ ] !\n1 →x | g →y\n", "ERROR: 3:10 stack underflow"),
        ("g : -- y\n\t[ ] !\n1 →x | { a g }\n", "ERROR: 3:8 a dict value is one value"),
    ],
)
def test_binders_and_dicts_refuse_at_their_position(source: str, error: str) -> None:
    """fpl/fon.py dict: a key given twice is refused where it repeats; a binder or a dict in
    the scope of another binder keeps its own position."""
    with pytest.raises(FplError) as caught:
        run(source)
    assert str(caught.value) == error


@pytest.mark.parametrize(
    "source",
    [
        "#x\u00b4\n",
        "#a/b\n",
        "{ a }\n",
        "{ 1 2 }\n",
        "{ a + }\n",
        "{ a (+ 1 2) }\n",
        "1 →x\u00b4\n",
        "1 →a/\n",
        "1 →a/b/\n",
        "1 →x | ../x\n",
    ],
)
def test_what_binders_do_not_yet_read_is_refused(source: str) -> None:
    """Hole unimplemented-words: a modified or path symbol; a dict with a key alone, a number
    key, or a value that is not one item pushing one value; a binder with a modifier or ending
    in a slash; and ../ to a bound name are refused before anything runs."""
    with pytest.raises(FplError) as caught:
        run(source)
    assert str(caught.value) == "ERROR: 1:1 no evaluator yet"


@pytest.mark.parametrize(
    ("source", "printed"),
    [
        ("m/\n\tsq : x -- y\n\t\tdup times\n3 m/sq\n", "9\n"),
        ("m/\n\tsq : x -- y\n\t\tdup times\n\tq : x -- y\n\t\tsq 1 +\n3 m/q\n", "10\n"),
        ("m/\n\tn/\n\t\tk : -- y\n\t\t\t5\nm/n/k\n", "5\n"),
        ("k : -- y\n\t3\nm/\n\tf : -- y\n\t\tk\nm/f\n", "3\n"),
        ("1 →a/b | a/b a/b +\n", "2\n"),
    ],
)
def test_a_head_ending_in_a_slash_mounts_its_children_as_a_directory(
    source: str, printed: str
) -> None:
    """draft3 examples/paths.fpl:1-5 (math/ holds mean and median, math/mean/doc reaches one);
    match examples/05-5-prolog-s-family.fpl:2 and 24 (family/parent): a path looks up through
    directories, a name in a body is looked up from its word outward (draft2 §scope follows
    the tree), and →a/b names a path for its line (server.fpl:19)."""
    assert run(source) == printed


@pytest.mark.parametrize(
    ("source", "printed"),
    [
        ("k : -- y\n\t3\nm/\n\tk : -- y\n\t\t4\n\tf : -- y\n\t\t../k\nm/f\n", "4\n"),
        ("k : -- y\n\t3\ng : -- y\n\t../k\ng\n", "3\n"),
        (
            "m/\n\tk : -- y\n\t\t1\n\tn/\n\t\tk : -- y\n\t\t\t2\n\t\tf : -- y\n\t\t\t../k\nm/n/f\n",
            "2\n",
        ),
    ],
)
def test_dot_dot_is_the_directory_enclosing_the_word(source: str, printed: str) -> None:
    """[D3.5] print : s -- +io takes ../io lexically: a word's body is its own directory
    (decision f, f/require), so .. is the directory the word is in; server.fpl:4 ../data and
    04-4-reactive-a.fpl:9 ../mouse/in reach the root from a top-level word."""
    assert run(source) == printed


BASE = "m/\n\tsq : x -- y\n\t\tdup times\n"


@pytest.mark.parametrize(
    ("source", "printed"),
    [
        (BASE + "s/\n\t#m bind\n\tf : x -- y\n\t\tsq\n3 s/f\n", "9\n"),
        (BASE + "s/\n\t#m bind\n3 s/sq\n", "9\n"),
        (BASE + "s/\n\tsq : x -- y\n\t\tdup +\n\t#m bind\n3 s/sq\n", "9\n"),
        (BASE + "s/\n\t#m bind\n\tsq : x -- y\n\t\tdup +\n3 s/sq\n", "6\n"),
    ],
)
def test_bind_appends_a_directory_to_the_log_and_later_shadows_earlier(
    source: str, printed: str
) -> None:
    """[D3.1] #math bind: an ordered log append (§5.2), later shadows earlier: a mount after a
    definition of the same name hides it, a definition after the mount hides the mount."""
    assert run(source) == printed


@pytest.mark.parametrize(
    ("source", "printed"),
    [
        ("f : -- y\n\t1\nf : -- y\n\t2\nf f/history\n", "2 ⟨ [ 1 ] ⟩\n"),
        ("f : -- y\n\t1\nf/history\n", "⟨⟩\n"),
        (BASE + "m/\n\tsq : x -- y\n\t\tdup +\nm/sq/history\n", "⟨ [ dup times ] ⟩\n"),
    ],
)
def test_history_holds_the_shadowed_definitions(source: str, printed: str) -> None:
    """[D3.3] math/mean/history: the shadowed definitions, oldest first, each as a quotation;
    the one in force is not among them."""
    assert run(source) == printed


@pytest.mark.parametrize(
    "source",
    [
        "m/\n",
        "m/\n\t1\n",
        "m/\n\t1 bind\n",
        "m/\n\t#nope bind\n",
        "m/\n\t#a/b bind\n",
        "a/b/\n\tk : -- y\n\t\t1\n",
        "../k\n",
        "m/ 1\n",
        "#m bind\n",
        "m/\n\tk : -- y\n\t\t1\nm\n",
        "k : -- y\n\t3\n../k\n",
        "a/b/\n\t{ a 1 a 2 }\n",
        "f : -- y\n\t1\nf/history/x\n",
    ],
)
def test_what_directories_do_not_yet_read_is_refused(source: str) -> None:
    """Hole unimplemented-words: code in a directory block, a bind of anything but a known
    #name, a path head, a head with tokens after its slash, ../ or bind at the top, a directory
    called as a word and a path into w/history are refused before anything runs."""
    with pytest.raises(FplError) as caught:
        run(source)
    assert str(caught.value) == "ERROR: 1:1 no evaluator yet"
