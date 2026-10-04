"""tokview.web and tokview.__main__: the server answers the page's three requests."""

import inspect
import io
import json
import threading
import urllib.error
import urllib.request
from collections.abc import Generator, Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, override

import pytest
from tokview import __main__ as cli
from tokview import web
from tokview.tokens import Tk, Tokenizers
from tokview.web import (
    PAGE,
    App,
    Opener,
    Response,
    claude_count,
    find_root,
    layout,
    send,
    server,
)

NOTE = "sq : x -- y\t; the square of x. Multiplying keeps its kind; an integer stays exact."


class FakeOpener:
    """Answers every request with a fixed count and keeps what it was sent."""

    def __init__(self) -> None:
        self.sent: list[urllib.request.Request] = []

    def __call__(self, request: urllib.request.Request) -> AbstractContextManager[Response]:
        self.sent.append(request)
        return nullcontext(io.BytesIO(b'{"input_tokens": 7}'))


@pytest.fixture
def root(tmp_path: Path) -> Path:
    examples = tmp_path / "features" / "x" / "examples"
    examples.mkdir(parents=True)
    (examples / "a.fpl").write_text("1 2 +\n\n")
    (examples / "a.expected").write_text("3\n")
    return tmp_path


@pytest.fixture
def opener() -> FakeOpener:
    return FakeOpener()


@contextmanager
def serving(app: App) -> Generator[str]:
    """The base URL of app served on a free port, for the length of the block."""
    httpd = server(app, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def url(root: Path, opener: FakeOpener) -> Iterator[str]:
    with serving(App(root, opener)) as base:
        yield base


def get(url: str) -> bytes:
    with urllib.request.urlopen(url) as response:
        body: bytes = response.read()
        return body


def post(url: str, body: object) -> dict[str, Any]:
    request = urllib.request.Request(f"{url}/tokenize", data=json.dumps(body).encode())
    answer: dict[str, Any] = json.loads(get_request(request))
    return answer


def get_request(request: urllib.request.Request) -> bytes:
    with urllib.request.urlopen(request) as response:
        body: bytes = response.read()
        return body


def test_the_page_is_served(url: str) -> None:
    assert get(f"{url}/") == PAGE.read_bytes()


def test_snippets_are_the_examples_by_feature_and_stem(url: str) -> None:
    assert json.loads(get(f"{url}/snippets")) == {"x/a": "1 2 +"}


@pytest.mark.parametrize(("wrap", "over"), [("as written", 1), ("folded", 0), ("ventilated", 0)])
def test_tokenize_round_trips_each_wrap(url: str, wrap: str, over: int) -> None:
    answer = post(url, {"text": NOTE, "tokenizer": "cl100k", "wrap": wrap, "width": 40})
    text = answer["text"]
    assert text == layout(NOTE, wrap, 40)[0]
    assert "".join(t["t"] for t in answer["tokens"]) == text
    assert b"".join(bytes.fromhex(t["h"]) for t in answer["tokens"]) == text.encode()
    assert answer["count"] == len(answer["tokens"])
    assert answer["lines"] == text.count("\n") + 1
    assert answer["over"] == over
    assert answer["claude"] is None


def test_a_split_character_has_no_text(url: str) -> None:
    answer = post(url, {"text": "😀", "tokenizer": "cl100k"})
    assert any(t["t"] is None for t in answer["tokens"])
    assert b"".join(bytes.fromhex(t["h"]) for t in answer["tokens"]) == "😀".encode()


def test_a_bad_request_is_refused(url: str) -> None:
    wrong: list[object] = [{"tokenizer": "gpt2"}, {"width": "wide"}, {"width": None}, [1], None]
    for body in wrong:
        with pytest.raises(urllib.error.HTTPError) as refused:
            post(url, body)
        assert refused.value.code == 400


def test_a_tokenizer_that_cannot_be_fetched_is_a_bad_gateway(root: Path) -> None:
    def unreachable() -> Tk:
        raise urllib.error.URLError("huggingface.co unreachable")

    app = App(root, tokenizers=Tokenizers({"t": unreachable}))
    with serving(app) as base, pytest.raises(urllib.error.HTTPError) as failed:
        post(base, {"tokenizer": "t"})
    assert failed.value.code == 502
    assert b"huggingface.co unreachable" in failed.value.read()


def test_an_empty_post_is_the_defaults(url: str) -> None:
    answer = json.loads(get_request(urllib.request.Request(f"{url}/tokenize", data=b"")))
    assert answer["text"] == ""
    assert answer["count"] == 0


def test_the_claude_count_needs_the_key(
    url: str, opener: FakeOpener, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert post(url, {"text": NOTE, "claude": True})["claude"] is None
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert post(url, {"text": NOTE, "claude": True})["claude"] == 7
    assert post(url, {"text": NOTE, "claude": False})["claude"] is None
    assert post(url, {"text": "  ", "claude": True})["claude"] is None
    assert len(opener.sent) == 1


def test_the_count_request(opener: FakeOpener) -> None:
    assert claude_count("dup times", "test-key", opener) == 7
    [request] = opener.sent
    assert request.full_url == "https://api.anthropic.com/v1/messages/count_tokens"
    assert request.get_method() == "POST"
    assert request.get_header("X-api-key") == "test-key"
    assert request.get_header("Anthropic-version") == "2023-06-01"
    assert isinstance(request.data, bytes)
    sent = json.loads(request.data)
    assert sent["messages"] == [{"role": "user", "content": "dup times"}]


def refusing(request: urllib.request.Request) -> AbstractContextManager[Response]:
    raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", Message(), None)


def unreachable(_: urllib.request.Request) -> AbstractContextManager[Response]:
    raise urllib.error.URLError("api.anthropic.com unreachable")


def answering(body: bytes) -> Opener:
    return lambda _: nullcontext(io.BytesIO(body))


@pytest.mark.parametrize(
    "failing",
    [
        refusing,
        unreachable,
        answering(b"<html>busy</html>"),
        answering(b'{"error": "overloaded"}'),
        answering(b"[7]"),
        answering(b'{"input_tokens": "many"}'),
    ],
)
def test_a_failed_count_is_no_count(failing: Opener) -> None:
    assert claude_count("dup times", "test-key", failing) is None


def test_a_failed_count_still_tokenizes(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with serving(App(root, refusing)) as base:
        answer = post(base, {"text": NOTE, "claude": True})
    assert answer["claude"] is None
    assert answer["count"] > 0


def test_the_count_follows_no_redirect() -> None:
    followed: list[str] = []

    class Moved(BaseHTTPRequestHandler):
        """Answers the POST with a redirect, and notes any request that follows it."""

        @override
        def log_message(self, format: str, *args: Any) -> None:
            """Quiet."""

        def do_POST(self) -> None:
            self.send_response(302)
            self.send_header("Location", "/elsewhere")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self) -> None:
            followed.append(self.path)
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Moved)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    request = urllib.request.Request(
        f"http://127.0.0.1:{httpd.server_port}/count",
        data=b"{}",
        headers={"x-api-key": "test-key"},
        method="POST",
    )
    try:
        with pytest.raises(urllib.error.HTTPError) as refused:
            send(request)
    finally:
        httpd.shutdown()
        httpd.server_close()
    assert refused.value.code == 302
    assert followed == []


def test_the_count_gives_up_in_finite_time(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[tuple[str, float]] = []

    def recording(request: urllib.request.Request, *, timeout: float) -> object:
        opened.append((request.full_url, timeout))
        return nullcontext(io.BytesIO(b""))

    monkeypatch.setattr(web.NO_REDIRECTS, "open", recording)
    send(urllib.request.Request(web.COUNT_URL))
    assert opened == [(web.COUNT_URL, web.TIMEOUT)]
    assert 0 < web.TIMEOUT < 600


def test_the_count_opens_through_send(root: Path) -> None:
    assert inspect.signature(claude_count).parameters["opener"].default is send
    assert App(root).opener is send


def test_a_code_line_past_the_width_is_over() -> None:
    assert layout("x" * 30, "as written", 20) == ("x" * 30, 1)
    assert layout("x" * 30 + "\t; a b", "folded", 20)[1] == 1


def test_the_root_is_found_upward(root: Path) -> None:
    deep = root / "tools" / "t" / "pkg"
    deep.mkdir(parents=True)
    assert find_root(deep) == root
    assert find_root(Path("/")) is None


def test_main_serves_and_prints_the_url(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    served: list[ThreadingHTTPServer] = []
    cli.main(["--port", "0", "--root", str(root)], served.append)
    [httpd] = served
    httpd.server_close()
    assert capsys.readouterr().out == f"tokview on http://127.0.0.1:{httpd.server_port}/\n"


def test_main_finds_the_root_or_asks_for_it(monkeypatch: pytest.MonkeyPatch) -> None:
    served: list[ThreadingHTTPServer] = []
    cli.main(["--port", "0"], served.append)
    served[0].server_close()

    def nowhere(_: Path) -> None:
        return None

    monkeypatch.setattr(cli, "find_root", nowhere)
    with pytest.raises(SystemExit):
        cli.main(["--port", "0"], served.append)
