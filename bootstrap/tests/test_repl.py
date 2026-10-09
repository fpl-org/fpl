"""The command line of a session: one input runs as its file does, an append is checked against
the head and durable before anything is printed, copies of a session answer alike, and the
loop enters what successive -e calls enter."""

import builtins
import contextlib
import os
import readline
import shutil
import tempfile
import threading
from collections.abc import Callable, Generator, Mapping, Sequence
from io import StringIO
from pathlib import Path
from typing import override

import pytest
from hypothesis import HealthCheck, assume, example, given, settings
from hypothesis import strategies as st
from test_desugar import programs
from test_session import POOL

from fpl.__main__ import main as run_file
from fpl.log import RefusedError, keyed, load, locked
from fpl.repl import USAGE, inputs, main, pending, provenance

SESSION = ["--session", "s.fon"]
SOURCES = programs | st.text(alphabet="ab1 \t\n[]:?-|", max_size=30)
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


def called(argv: Sequence[str], env: Mapping[str, str], stdin: str = "") -> tuple[int, str, str]:
    """The exit status, stdout and stderr of a call reading `stdin`."""
    out, err = StringIO(), StringIO()
    code = main(list(argv), StringIO(stdin), out, err, env)
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
@example("->x")
@example("--")
@example("-e")
@example("")
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
        code, _, err = called([*SESSION, "--head", str(len(inputs)), "-e", "1"], env)
        assert (code < 2, err.splitlines()[-1].startswith(f"HEAD {len(inputs) + 1} $")) == (
            True,
            True,
        )
        assert len(load(work / "s.fon", keyed(env)).events) == len(inputs) + 1


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
            main([*SESSION, "-e", text], StringIO(), Recorded(events), StringIO(), env)
            last = len(events) - events[::-1].index("fsync") - 1
            assert last < events.index("write")


@pytest.mark.parametrize(
    "argv",
    [
        ["--log", "--show"],
        ["--at", "0", "--head", "0"],
        ["--bogus", "--log"],
        ["--fuel", "x", "--log"],
        ["--fuel", "01", "--log"],
        ["--fuel", str(1 << 64), "--log"],
        ["--at", "0", "--head", "0", "-e", "1"],
        ["--at", "0", "--rewind", "0"],
        ["--at", "0", "--log"],
        ["-h"],
        ["--help"],
        ["--canon", "-e", "1"],
        ["--sess", "s.fon", "--log"],
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


COMPLETE = [text for text in POOL if text.strip()]


@given(st.lists(st.sampled_from(COMPLETE), max_size=5))
def test_the_loop_enters_what_calls_enter(texts: list[str]) -> None:
    """[law: interactive] the interactive loop over blank-line-joined inputs writes the same
    log bytes as the same inputs given as successive -e calls."""
    joined = "\n".join(texts)
    lines = iter(joined.splitlines())
    assert list(inputs(lambda _: next(lines, None))) == texts
    with session() as (work, env):
        assert called(SESSION, env, joined)[0] == 0
        copy = work.with_name("copy")
        copy.mkdir()
        with contextlib.chdir(copy):
            for text in texts:
                called([*SESSION, "-e", text], env)
        assert files(work) == files(copy)


@pytest.mark.parametrize(
    ("text", "on"),
    [
        ("1\n", False),
        ("1 [\n", True),
        ("1 ⟨\n", True),
        (")\n", False),
        ("f : -- x\n", True),
        ("f : -- x\n\t2\n", True),
        ("1\n\t2\n", True),
        ("a/\n", True),
        (":show\n", False),
    ],
)
def test_pending(text: str, on: bool) -> None:
    """An input goes on while a pair is open, after a head or a block, or after a trailing /."""
    assert pending(text) is on


def fed(lines: Sequence[str]) -> list[str]:
    """The inputs the lines make, as the loop groups them."""
    feed = iter(lines)
    return list(inputs(lambda _: next(feed, None)))


@pytest.mark.parametrize(
    ("lines", "made"),
    [
        (["f : -- x", "2", ""], ["f : -- x\n\t2\n"]),
        (["f : -- x", "\t2", ""], ["f : -- x\n\t2\n"]),
        (["f : -- x", "  2", ""], ["f : -- x\n  2\n"]),
        (["a", "f : -- x", "\tg : -- y", "2", ""], ["a\n", "f : -- x\n\tg : -- y\n\t\t2\n"]),
        (["f : -- x", "2", "3", ""], ["f : -- x\n\t2\n3\n"]),
        (["f : -- x", "", "2"], ["f : -- x\n", "2\n"]),
        (["1 [", "2 ]"], ["1 [\n2 ]\n"]),
        (["a/", "2"], ["a/\n2\n"]),
    ],
)
def test_a_body_at_the_margin(lines: list[str], made: list[str]) -> None:
    """A line at the margin right after a definition head is the body's first, one tab deeper
    than the head; one that starts with a space or a tab, one after the body's first line or
    a line that is no head, and one after a blank line, are left as they were written."""
    assert fed(lines) == made


@given(
    st.sampled_from(["f : -- x", "f : n -- n ; note"]),
    st.from_regex(r"[^ \t\n\r].{0,8}", fullmatch=True),
)
def test_a_body_is_read_with_or_without_its_tab(header: str, body: str) -> None:
    """[law: body-margin] the lines of a head, a body at the margin and a blank line make the
    inputs they make with the body one tab in."""
    assume(body.isprintable())
    assert fed([header, body, ""]) == fed([header, "\t" + body, ""])


def test_a_definition_without_tabs() -> None:
    """The stream reader takes the unindented line after a head for the body, so the word it
    defines works; in one-shot, a file's own rule holds."""
    typed = "plus-one : n -- n\n1 +\n1 2 3 plus-one\n"
    assert called([], {}, typed) == (0, "2 3 4\n", "")
    assert called([], {}, "plus-one : n -- n\n  1 +\n")[1].startswith("ERROR: 2:1 indentation")


def test_a_definition_without_a_body_is_noted() -> None:
    """A definition whose head has no code under it is the identity, and the loop says so,
    naming the word and where its head is, before the input's other notes, also when the input
    then fails; one with a body, a one-shot input and a command are not noted."""
    note = "NOTE 1:1 plus-one has an empty body, which is the identity\n"
    assert called([], {}, "plus-one : n -- n\n\n1 2 3 plus-one\n") == (0, "1 2 3\n", note)
    assert called([], {}, "plus-one : n -- n\n") == (0, "", note)
    assert called([], {}, "plus-one : n -- n\n;; doc\n") == (0, "", note)
    nested = called([], {}, "a/\n\tb : -- x\n\n:show\n")
    assert nested[2].startswith("NOTE 2:2 b has an empty body, which is the identity\n")
    assert called([], {}, "f : -- x\n\t2\n\nf\n:show\n")[2] == ""
    assert called(["-e", "plus-one : n -- n"], {}) == (0, "", "")
    code, out, err = called([], {}, "1 [\n")
    assert (code, out.startswith("ERROR: ")) == (0, True)
    assert "NOTE" not in err


def test_a_note_comes_before_the_head() -> None:
    """In a session the NOTE comes first and the new head last."""
    with session() as (_, env):
        notes = called(SESSION, env, "f : -- x\n\n")[2].splitlines()
    assert notes[0] == "NOTE 1:1 f has an empty body, which is the identity"
    assert notes[-1].startswith("HEAD 1 $")


def test_the_loop_in_memory() -> None:
    """Without --session the loop keeps its log in memory and names no head; commands list,
    show, rewind and toggle the canonical form; an unknown command is told and passed over."""
    typed = "f : -- x\n\t2\n\nf\n:log\n:show\n:canonical\n1  2\n:rewind 0\nf\n:bogus\n:quit\n3\n"
    code, out, err = called([], {}, typed)
    rows = out.splitlines()
    assert (code, err, rows[0]) == (0, "f\n^\n", "2")
    assert [row.rsplit(" ", 1)[0] for row in rows[1:3]] == ["1 input ok 0 -", "2 input ok 1 -"]
    assert rows[3:] == [
        "f : -- x",
        "\t2",
        "f",
        "1 2",
        "1 2",
        "f",
        "ERROR: 1:1 no evaluator yet",
        "ERROR: unknown command",
    ]


def test_the_loop_as_of_an_event() -> None:
    """With --at every input is evaluated at that event and nothing is appended."""
    with session() as (work, env):
        called([*SESSION, "-e", "f : -- x\n\t2\n"], env)
        before = files(work)
        shown = (0, "2\n2\nf : -- x\n\t2\n", "")
        assert called([*SESSION, "--at", "1"], env, "f\nf\n:show\n") == shown
        assert files(work) == before


def test_a_log_refused_at_start() -> None:
    """A session that does not load stops the loop before it reads."""
    with session() as (work, env):
        (work / "s.fon").write_text("1\n")
        code, out, _ = called(SESSION, env, "1\n")
        assert (code, out.startswith("ERROR: s.fon:1 ")) == (2, True)


class Terminal(StringIO):
    """A stream that says it is a terminal."""

    @override
    def isatty(self) -> bool:
        return True


def test_the_loop_at_a_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """At a terminal the loop prompts through input(); an append from elsewhere moves the head,
    so the next input is refused, and the one after appends at the head it adopted."""
    prompts: list[str] = []
    with session() as (_, env):
        lines = iter(["1", "", "g : -- x", "\t3", "", "4"])

        def typed(prompt: str) -> str:
            prompts.append(prompt)
            if len(prompts) == 2:
                called([*SESSION, "-e", "7"], env)
            line = next(lines, None)
            if line is None:
                raise EOFError
            return line

        bindings: list[str] = []
        monkeypatch.setattr(builtins, "input", typed)
        monkeypatch.setattr(readline, "parse_and_bind", bindings.append)
        out, err = StringIO(), StringIO()
        assert main([*SESSION, "--head", "0"], Terminal(), out, err, env) == 0
        assert out.getvalue() == "1\nERROR: head moved: the head is 2\n4\n"
        heads = [row.split(" ", 2)[:2] for row in err.getvalue().splitlines()]
        assert heads == [["HEAD", "1"], ["HEAD", "3"]]
        assert prompts == ["fpl> "] * 3 + ["...  "] * 2 + ["fpl> "] * 2
        assert bindings == ["tab: self-insert"]


def test_a_definition_at_a_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """At a terminal the body typed without its tab is the body, as a prompt of continuation
    after the head; an empty line ends the input."""
    prompts: list[str] = []
    lines = iter(["plus-one : n -- n", "1 +", "", "1 2 3 plus-one"])

    def typed(prompt: str) -> str:
        prompts.append(prompt)
        line = next(lines, None)
        if line is None:
            raise EOFError
        return line

    monkeypatch.setattr(builtins, "input", typed)
    bindings: list[str] = []
    monkeypatch.setattr(readline, "parse_and_bind", bindings.append)
    out, err = StringIO(), StringIO()
    assert main([], Terminal(), out, err, {}) == 0
    assert (out.getvalue(), err.getvalue()) == ("2 3 4\n", "")
    assert prompts == ["fpl> ", "...  ", "...  ", "fpl> ", "fpl> "]


def test_in_memory() -> None:
    """Without --session the log is empty: --log lists nothing and --at 0 evaluates the input
    alone, each exiting 0."""
    assert called(["--log"], {}) == (0, "", "")
    assert called(["--at", "0", "-e", "1 2"], {}) == (0, "1 2\n", "")


def test_provenance() -> None:
    """Either variable makes the input an agent's and is recorded as given, the other empty;
    either is refused unless printable ASCII."""
    assert provenance({}) == ("operator", "", "")
    assert provenance({"FPL_MODEL": "m"}) == ("agent", "m", "")
    assert provenance({"FPL_SESSION_ID": "s"}) == ("agent", "", "s")
    with pytest.raises(RefusedError, match=r"^\$FPL_SESSION_ID is not printable ASCII"):
        provenance({"FPL_SESSION_ID": "é"})


def test_a_goal_is_noted_at_its_place_in_its_input() -> None:
    """A goal in the second input is noted at its line in that input."""
    with session() as (_, env):
        called([*SESSION, "-e", "1"], env)
        assert called([*SESSION, "-e", "2 ?"], env)[2].startswith("GOAL 1:3 ")


def test_an_append_waits_for_the_lock() -> None:
    """An append takes the session's lock: while another holds it, nothing is written."""
    with session() as (work, env):
        path = work / "s.fon"
        writer = threading.Thread(target=called, args=([*SESSION, "-e", "1"], env))
        with locked(path):
            writer.start()
            writer.join(0.2)
            assert (writer.is_alive(), path.exists()) == (True, False)
        writer.join()
        assert len(load(path, keyed(env)).events) == 1


def test_the_loop_checks_a_given_head() -> None:
    """--head given to the loop is the head its first input is checked against."""
    with session() as (_, env):
        called([*SESSION, "-e", "1"], env)
        refused = (0, "ERROR: head moved: the head is 1\n", "")
        assert called([*SESSION, "--head", "0"], env, "5\n") == refused


def test_log_and_rewind_ignore_at() -> None:
    """In a loop as of an event, :log lists and :rewind appends as they do without --at."""
    with session() as (work, env):
        for text in ("1", "2"):
            called([*SESSION, "-e", text], env)
        code, out, _ = called([*SESSION, "--at", "9"], env, ":log\n:rewind 1\n")
        rows = [row.rsplit(" ", 1)[0] for row in out.splitlines()]
        assert (code, rows) == (0, ["1 input ok 0 -", "2 input ok 1 -"])
        kinds = [event.kind for event in load(work / "s.fon", keyed(env)).events]
        assert kinds == ["input", "input", "rewind"]


def test_the_loop_as_of_an_event_checks_no_head(monkeypatch: pytest.MonkeyPatch) -> None:
    """A loop as of an event checks no head, so an append from elsewhere does not refuse it."""
    with session() as (_, env):
        called([*SESSION, "-e", "f : -- x\n\t2\n"], env)
        replies = iter(["f", "append", "f"])

        def typed(_prompt: str) -> str:
            reply = next(replies, None)
            if reply == "append":
                called([*SESSION, "-e", "7"], env)
                reply = next(replies)
            if reply is None:
                raise EOFError
            return reply

        monkeypatch.setattr(builtins, "input", typed)
        out, err = StringIO(), StringIO()
        assert main([*SESSION, "--at", "1"], Terminal(), out, err, env) == 0
        assert (out.getvalue(), err.getvalue()) == ("2\n2\n", "")


def _as_given(_work: Path, env: dict[str, str]) -> dict[str, str]:
    """Nothing prepared."""
    return env


def _a_directory(work: Path, env: dict[str, str]) -> dict[str, str]:
    """A directory where the log goes."""
    (work / "s.fon").mkdir()
    return env


def _unwritable(work: Path, env: dict[str, str]) -> dict[str, str]:
    """A working directory no file can be made in."""
    work.chmod(0o500)
    return env


def _key_unwritable(work: Path, env: dict[str, str]) -> dict[str, str]:
    """A key file in a directory no file can be made in."""
    keys = work.parent / "keys"
    keys.mkdir(mode=0o500)
    return {**env, "FPL_LOG_KEY": f"{keys}/key"}


def _no_home(_work: Path, _env: dict[str, str]) -> dict[str, str]:
    """No variable that names a key file."""
    return {}


@pytest.mark.parametrize(
    ("argv", "stdin", "made", "named"),
    [
        (["--session", "gone/s.fon", "-e", "1"], "", _as_given, "gone/s.fon"),
        (["--session", "gone/s.fon"], "1\n", _as_given, "gone/s.fon"),
        ([*SESSION, "--log"], "", _a_directory, "s.fon"),
        ([*SESSION, "-e", "1"], "", _a_directory, "s.fon"),
        ([*SESSION, "-e", "1"], "", _unwritable, "s.fon"),
        ([*SESSION, "--show"], "", _key_unwritable, "keys/key"),
        ([*SESSION, "--log"], "", _no_home, "$HOME"),
    ],
)
def test_a_path_refused(
    argv: list[str],
    stdin: str,
    made: Callable[[Path, dict[str, str]], dict[str, str]],
    named: str,
) -> None:
    """A path the system refuses, or none to find the key by, is a refusal: one ERROR line
    naming it, exit 2, and nothing written but a lock."""
    with session() as (work, given):
        env = made(work, given)
        before = files(work)
        try:
            code, out, err = called(argv, env, stdin)
        finally:
            work.chmod(0o700)
        assert (code, err, out.count("\n")) == (2, "", 1)
        assert out.startswith("ERROR: ")
        assert named in out
        after = {path: data for path, data in files(work).items() if path.suffix != ".lock"}
        assert after == before
