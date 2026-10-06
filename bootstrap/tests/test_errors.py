"""The shape of an error: one `.expected` line, and a caret that lands on the column."""

from hypothesis import given
from hypothesis import strategies as st

from fpl.errors import FplError, Span

positions = st.integers(min_value=1, max_value=10_000)
messages = st.text(alphabet=st.characters(blacklist_categories=["Cc", "Cs"]), min_size=1)


@given(positions, positions, messages)
def test_the_error_line_is_what_an_expected_file_holds(line: int, col: int, message: str) -> None:
    error = FplError(Span(line, col), message)
    assert str(error) == f"ERROR: {line}:{col} {message}"
    assert error.args == (message,)


@given(st.text(alphabet="ab", max_size=10), st.integers(min_value=1, max_value=5))
def test_a_caret_past_the_end_of_the_line_stops_just_after_it(text: str, beyond: int) -> None:
    error = FplError(Span(1, len(text) + 1 + beyond), "x")
    assert error.render(text or " ").split("\n")[2] == " " * len(text or " ") + "^"


@given(
    st.lists(st.text(alphabet="ab ", min_size=1, max_size=20), min_size=1, max_size=5), st.data()
)
def test_the_caret_sits_under_the_column(lines: list[str], data: st.DataObject) -> None:
    line = data.draw(st.integers(min_value=1, max_value=len(lines)))
    col = data.draw(st.integers(min_value=1, max_value=len(lines[line - 1]) + 1))
    error = FplError(Span(line, col), "here")
    head, text, caret = error.render("\n".join(lines)).split("\n")
    assert (head, text) == (str(error), lines[line - 1])
    assert caret == " " * (col - 1) + "^"


@given(st.text(alphabet="ab\n", max_size=30), positions)
def test_a_line_outside_the_source_gives_the_error_line_alone(source: str, col: int) -> None:
    beyond = len(source.splitlines()) + 1
    error = FplError(Span(beyond, col), "gone")
    assert error.render(source) == str(error)
