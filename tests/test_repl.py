"""The command line of a session: one input runs as its file does, an append is checked against
the head and durable before anything is printed, and copies of a session answer alike."""

import contextlib
import os
import shutil
import tempfile
from collections.abc import Generator, Mapping, Sequence
from io import StringIO
from pathlib import Path
from typing import override

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from test_desugar import programs
from test_session import POOL

from fpl.__main__ import main as run_file
from fpl.log import keyed, load
from fpl.repl import USAGE, main

SESSION = ["--session", "s.fon"]
SOURCES = (programs | st.text(alphabet="ab1 \t\n[]:?-|", max_size=30)).filter(
    lambda s: not s.startswith("-")
)
texts = st.sampled_from(POOL)
seqs = st.integers(0, 6).map(str)
command = st.one_of(
    texts.map(lambda t: ["-e", t]),
    texts.map(lambda t: ["--canonical", "-e", t]),
    seqs.map(lambda k: ["--rewind", k]),
    st.tuples(seqs, texts).map(lambda p: ["--at", p[0], "-e", p[1]]),
    st.tuples(seqs, texts).map(lambda p: ["--head", p[0], "-e", p[1]]),
    st.sampled_from([["--log"], ["--show"]]),
)


def called(argv: Sequence[str], env: Mapping[str, str]) -> tuple[int, str, str]:
    """The exit status, stdout and stderr of a call."""
    out, err = StringIO(), StringIO()
    code = main(list(argv), out, err, env)
    return code, out.getvalue(), err.getvalue()


def files(root: Path) -> dict[Path, bytes]:
    """Every file under root, by its path from root, and its bytes."""
    return {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@contextlib.contextmanager
def session() -> Generator[tuple[Path, dict[str, str]]]:
    """A fresh directory to work in, and an environment whose key lies beside it."""
    with tempfile.TemporaryDirectory() as root:
        work = Path(root, "work")
        work.mkdir()
        with contextlib.chdir(work):
            yield work, {"FPL_LOG_KEY": f"{root}/key", "HOME": root}


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(SOURCES)
def test_one_input_runs_as_its_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], source: str
) -> None:
    """[law: one-shot-is-file] main(["-e", s]) gives the same stdout, stderr and exit code as
    python -m fpl on a file holding s plus a newline."""
    file = tmp_path / "p.fpl"
    file.write_text(source + "\n")
    code = run_file([str(file)])
    shown = capsys.readouterr()
    assert called(["-e", source], {}) == (code, shown.out, shown.err)


@given(st.lists(command, max_size=4), st.lists(command, min_size=1, max_size=3))
def test_copies_of_a_session_answer_alike(history: list[list[str]], calls: list[list[str]]) -> None:
    """[law: determinism] two copies of a session directory given the same argv, env and key
    produce byte-identical stdout, stderr, exit code and file bytes."""
    with session() as (work, env):
        for argv in history:
            called(SESSION + argv, env)
        copy = work.with_name("copy")
        shutil.copytree(work, copy)
        for argv in calls:
            first = called(SESSION + argv, env)
            with contextlib.chdir(copy):
                assert called(SESSION + argv, env) == first
        assert files(work) == files(copy)


@given(st.lists(texts, min_size=1, max_size=4), st.data())
def test_a_stale_head_is_refused(inputs: list[str], data: st.DataObject) -> None:
    """[law: stale-head] an append whose --head is not the head exits 2 with one ERROR line
    and leaves the file bytes unchanged."""
    with session() as (work, env):
        for text in inputs:
            called([*SESSION, "-e", text], env)
        stale = str(data.draw(st.integers(0, len(inputs) - 1)))
        action = data.draw(st.sampled_from([["-e", "1"], ["--rewind", "0"]]))
        before = files(work)
        refused = (2, f"ERROR: head moved: the head is {len(inputs)}\n", "")
        assert called([*SESSION, "--head", stale, *action], env) == refused
        assert files(work) == before


class Recorded(StringIO):
    """A stream that notes each write in a shared list."""

    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self.events = events

    @override
    def write(self, s: str) -> int:
        self.events.append("write")
        return super().write(s)


@given(st.lists(texts, min_size=1, max_size=3))
def test_an_append_is_durable_before_it_is_printed(inputs: list[str]) -> None:
    """[law: write-ahead] the last fsync of an append happens before the first write to
    stdout."""
    events: list[str] = []
    fsync = os.fsync

    def recorded(fd: int) -> None:
        events.append("fsync")
        fsync(fd)

    with session() as (_, env), pytest.MonkeyPatch.context() as patch:
        patch.setattr(os, "fsync", recorded)
        for text in inputs:
            events.clear()
            main([*SESSION, "-e", text], Recorded(events), StringIO(), env)
            last = len(events) - events[::-1].index("fsync") - 1
            assert last < events.index("write")


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--log", "--show"],
        ["--bogus", "--log"],
        ["--fuel", "x", "--log"],
        ["--fuel", "01", "--log"],
        ["--fuel", str(1 << 64), "--log"],
        ["--at", "0", "--head", "0", "-e", "1"],
        ["--at", "0", "--rewind", "0"],
        ["--at", "0", "--log"],
    ],
)
def test_argv_not_taken(argv: list[str]) -> None:
    """argv the command line does not take prints the usage line alone and exits 2."""
    assert called(argv, {}) == (2, "", USAGE + "\n")


@pytest.mark.parametrize(
    ("argv", "env", "message"),
    [
        (["--rewind", "0"], {}, "nothing to rewind"),
        (["--at", "1", "--show"], {}, "no event 1"),
        (["--at", "$0:0:0", "--show"], {}, "no event $0:0:0"),
        (["-e", "\udc80"], {}, "the input is not UTF-8"),
        (["-e", "1"], {"FPL_MODEL": "é"}, "$FPL_MODEL is not printable ASCII of at most 256"),
    ],
)
def test_refused(argv: list[str], env: dict[str, str], message: str) -> None:
    """A refusal prints one ERROR line to stdout and exits 2."""
    code, out, err = called(argv, env)
    assert (code, err) == (2, "")
    assert out.startswith(f"ERROR: {message}")
    assert out.count("\n") == 1


def test_a_session() -> None:
    """Inputs append at the head and name it; the log lists them, --show joins the program,
    a rewind returns to an earlier state, and --at evaluates without appending."""
    with session() as (work, env):
        assert called([*SESSION, "-e", "f : -- x\n\t2\n"], env)[:2] == (0, "")
        code, out, err = called([*SESSION, "-e", "f"], env)
        assert (code, out) == (0, "2\n")
        assert err.startswith("HEAD 2 $45600:")
        second = err.removeprefix("HEAD 2 ").strip()
        assert called([*SESSION, "--at", second, "--show"], env) == (0, "f : -- x\n\t2\nf\n", "")
        assert called([*SESSION, "--rewind", "1"], env)[:2] == (0, "")
        assert called([*SESSION, "--show"], env) == (0, "f : -- x\n\t2\n", "")
        before = files(work)
        assert called([*SESSION, "--at", "2", "-e", "f"], env) == (0, "2\n", "")
        assert files(work) == before
        listed = called([*SESSION, "--log"], env)[1].splitlines()
        assert [row.rsplit(" ", 1)[0] for row in listed] == [
            "1 input ok 0 -",
            "2 input ok 1 -",
            "3 rewind ok 1 2",
        ]
        assert listed[1].endswith(second)
        events = load(work / "s.fon", keyed(env)).events
        assert called([*SESSION, "--at", events[0].ident.raw().hex(), "--show"], env)[1] == (
            "f : -- x\n\t2\n"
        )
        assert b"who operator" in (work / "s.fon").read_bytes()


def test_an_input_that_fails() -> None:
    """A failing input is appended as an error, exits 1 and prints its ERROR line; the caret
    goes to stderr before the head."""
    with session() as (_, env):
        code, out, err = called([*SESSION, "--canonical", "-e", "1 ["], {**env, "FPL_MODEL": "m"})
        assert (code, out) == (1, "ERROR: 1:3 [ never closed\n")
        assert err.splitlines()[-1].startswith("HEAD 1 $")
        assert "who agent" in (Path("s.fon")).read_text()
        code, out, _ = called([*SESSION, "--fuel", "0", "-e", "1"], env)
        assert (code, out) == (1, "ERROR: 1:1 out of fuel\n")


def test_canonical() -> None:
    """--canonical prints the input as the printer writes it, before its output."""
    plain = called(["-e", "1  2  +"], {})[1]
    assert called(["--canonical", "-e", "1  2  +"], {}) == (0, "1 2 +\n" + plain, "")


def test_the_head_cannot_be_the_rewind_target() -> None:
    """A rewind to the head is refused and writes nothing."""
    with session() as (work, env):
        called([*SESSION, "-e", "1"], env)
        before = files(work)
        assert called([*SESSION, "--rewind", "1"], env) == (
            2,
            "ERROR: cannot rewind to the head\n",
            "",
        )
        assert files(work) == before


def test_a_refused_log() -> None:
    """A session file that does not load is refused with its line."""
    with session() as (work, env):
        (work / "s.fon").write_text("1\n")
        code, out, _ = called([*SESSION, "--log"], env)
        assert (code, out.startswith("ERROR: s.fon:1 ")) == (2, True)
