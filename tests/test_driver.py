"""Running a program never lets anything but an FplError out."""

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fpl.driver import run
from fpl.errors import FplError


@given(st.text(max_size=40))
def test_nothing_runs_before_there_is_a_language(source: str) -> None:
    with pytest.raises(FplError):
        run(source, Path("/nonexistent/grammar.lark"))


def test_a_parse_is_not_yet_a_run(tmp_path: Path) -> None:
    grammar = tmp_path / "g.lark"
    grammar.write_text('start: "x"\n')
    with pytest.raises(FplError) as caught:
        run("x", grammar)
    assert str(caught.value) == "ERROR: 1:1 no evaluator yet"
