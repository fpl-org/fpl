"""Every maintainer-written example runs to its `.expected` output (.agents/CONVENTIONS.md)."""

from pathlib import Path

import pytest
from corpus import PROGRAMS

from fpl.driver import run
from fpl.errors import FplError, UnresolvedError

PLACEHOLDER = "ERROR: 1:1 no evaluator yet\n"
EXAMPLES = [p for p in PROGRAMS if p.parts[-3] != "_template"]
UNRESOLVED = {
    "draft1/draft1": "no evaluator yet: newline",
    "draft2/03-operatives-thunks": "no evaluator yet: ../debug",
    "draft2/05-the-dictionary-is": "no evaluator yet: select",
    "draft2/06-constructors-run-backwards": "no evaluator yet: unpair",
    "draft2/08-objects-are-directories": "no evaluator yet: dict",
    "draft2/11-laziness": "no evaluator yet: curry",
    "draft3/paths": "no evaluator yet: shape",
    "match/01-1-constructors-run": "no evaluator yet: pos",
    "match/02-2-the-same": "unknown word: circle",
    "match/03-3-multiple-dispatch": "unknown word: Asteroid",
    "match/04-4-list-patterns": "no evaluator yet: false",
    "match/05-5-prolog-s-family": "unknown word: x",
    "sketch/05-5-multiple-dispatch": "unknown word: shape/kind",
}
"""The examples whose `.expected` holds the skeleton's blanket refusal for a call nothing
answers, each with the refusal it gets now, at its word. Only these are mapped back to the
placeholder, so another example that starts failing so, or one of these whose word changes
(PLANNED moved), fails a test; the owner rewrites the `.expected` files and drops the map."""


def name(program: Path) -> str:
    """The suite and the example, as the tests and UNRESOLVED name it."""
    return f"{program.parts[-3]}/{program.stem}"


def output(program: Path) -> str:
    """What `python -m fpl` prints for a program: its output, or its one error line. A call
    nothing answers is told at its word there, but the maintainer's `.expected` files of the
    programs in UNRESOLVED still hold the skeleton's blanket refusal, and it stands for them
    here until they are rewritten (hole unimplemented-words)."""
    try:
        return run(program.read_text())
    except FplError as error:
        mapped = isinstance(error, UnresolvedError) and name(program) in UNRESOLVED
        return PLACEHOLDER if mapped else f"{error}\n"


@pytest.mark.parametrize("program", EXAMPLES, ids=[name(p) for p in EXAMPLES])
def test_example(program: Path) -> None:
    assert output(program) == program.with_suffix(".expected").read_text()


@pytest.mark.parametrize("example", sorted(UNRESOLVED))
def test_the_word_a_placeholder_stands_for(example: str) -> None:
    """Each mapped example still fails at the word recorded, and its `.expected` is the
    placeholder: a word that moves in or out of PLANNED, or a fixture rewritten, breaks this."""
    (program,) = (p for p in EXAMPLES if name(p) == example)
    with pytest.raises(UnresolvedError) as caught:
        run(program.read_text())
    assert caught.value.message == UNRESOLVED[example]
    assert program.with_suffix(".expected").read_text() == PLACEHOLDER
