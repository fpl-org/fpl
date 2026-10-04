"""The command line: output or one error line, and an exit status that says which."""

from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from fpl.__main__ import main
from fpl.errors import FplError, Span


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.text(alphabet="ab \n", max_size=30).map("a".__add__))
def test_a_file_that_cannot_run_prints_one_error_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], source: str
) -> None:
    """A file that does not run exits 1 and prints exactly one line, starting `ERROR: `."""
    program = tmp_path / "p.fpl"
    program.write_text(source)
    assert main([str(program)]) == 1
    out = capsys.readouterr().out
    assert out.startswith("ERROR: ")
    assert out.count("\n") == 1


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.text(alphabet="ab \n", max_size=30), st.text(alphabet="xy", min_size=1, max_size=10))
def test_the_caret_goes_to_stderr_and_the_error_line_to_stdout(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    message: str,
) -> None:
    error = FplError(Span(1, 2), message)

    def run(_source: str) -> str:
        raise error

    monkeypatch.setattr("fpl.__main__.run", run)
    program = tmp_path / "p.fpl"
    program.write_text(source)
    assert main([str(program)]) == 1
    shown = error.render(source).partition("\n")[2]
    assert capsys.readouterr() == (f"{error}\n", shown + "\n" if shown else "")


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.text(max_size=30))
def test_a_file_that_runs_prints_its_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    output: str,
) -> None:
    seen: list[str] = []

    def run(source: str) -> str:
        seen.append(source)
        return output

    monkeypatch.setattr("fpl.__main__.run", run)
    program = tmp_path / "p.fpl"
    program.write_text("the program")
    assert main([str(program)]) == 0
    assert (capsys.readouterr().out, seen) == (output, ["the program"])


def test_it_wants_exactly_one_file(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert capsys.readouterr().err == "usage: python -m fpl <file.fpl>\n"
