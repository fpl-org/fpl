"""tokview.web and tokview.__main__: the server answers the page's three requests."""

import io
import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import AbstractContextManager, nullcontext
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from tokview import __main__ as cli
from tokview.web import PAGE, App, Response, claude_count, find_root, layout, server

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


@pytest.fixture
def url(root: Path, opener: FakeOpener) -> Iterator[str]:
    httpd = server(App(root, opener), 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    httpd.server_close()


def get(url: str) -> bytes:
    with urllib.request.urlopen(url) as response:
        body: bytes = response.read()
        return body


def post(url: str, body: dict[str, Any]) -> dict[str, Any]:
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
    for body in [{"tokenizer": "gpt2"}, {"width": "wide"}]:
        with pytest.raises(urllib.error.HTTPError) as refused:
            post(url, body)
        assert refused.value.code == 400


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
