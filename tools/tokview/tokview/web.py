"""The page's server: the page, the example snippets, and a text laid out and tokenized.

    GET /            the page
    GET /snippets    {"<feature>/<file>": text} of features/*/examples/*.fpl under the root
    POST /tokenize   {"text", "tokenizer", "wrap", "width", "claude"} ->
                     {"text": the laid-out text, "tokens": [{"t": text or null, "h": hex bytes,
                      "id": int, "n": byte length}], "count", "lines", "over", "claude"}

The Claude count comes from Anthropic's token-counting endpoint, which is not a model call,
and only when ANTHROPIC_API_KEY is set; otherwise it is null.
"""

import json
import os
import urllib.request
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Protocol, override

from tokview.tokens import Tokenizers
from tokview.wrap import cols, folded, ventilated

PAGE = Path(__file__).with_name("static") / "tokview.html"
COUNT_URL = "https://api.anthropic.com/v1/messages/count_tokens"
MODEL = "claude-opus-5-5"


class Response(Protocol):
    """What the token-counting call reads from an opened request."""

    def read(self) -> bytes:
        """The whole response body."""
        ...


Opener = Callable[[urllib.request.Request], AbstractContextManager[Response]]


def claude_count(text: str, key: str, opener: Opener = urllib.request.urlopen) -> int:
    """Claude's token count of text as one user message, from the counting endpoint."""
    request = urllib.request.Request(
        COUNT_URL,
        data=json.dumps({"model": MODEL, "messages": [{"role": "user", "content": text}]}).encode(),
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    with opener(request) as response:
        return int(json.loads(response.read())["input_tokens"])


def layout(text: str, wrap: str, width: int) -> tuple[str, int]:
    """Text under a wrap mode (folded, ventilated, else as written), and how many code lines
    stay wider than width."""
    if wrap == "folded":
        return folded(text, width)
    laid = ventilated(text) if wrap == "ventilated" else text
    return laid, sum(cols(line) > width for line in laid.split("\n"))


def find_root(start: Path) -> Path | None:
    """The nearest directory at or above start that holds features/."""
    return next((d for d in (start, *start.parents) if (d / "features").is_dir()), None)


@dataclass
class App:
    """What a request needs: the checkout's root, the tokenizers, and how to open a URL."""

    root: Path
    opener: Opener = urllib.request.urlopen
    tokenizers: Tokenizers = field(default_factory=Tokenizers)

    def snippets(self) -> dict[str, str]:
        """The example programs under the root, by "<feature>/<file stem>"."""
        paths = sorted(self.root.glob("features/*/examples/*.fpl"))
        return {f"{p.parent.parent.name}/{p.stem}": p.read_text().rstrip("\n") for p in paths}

    def tokenize(self, request: dict[str, Any]) -> dict[str, Any]:
        """The answer to POST /tokenize; a malformed request is a ValueError."""
        tk = self.tokenizers.get(str(request.get("tokenizer", "o200k")))
        text, over = layout(
            str(request.get("text", "")),
            str(request.get("wrap", "as written")),
            int(request.get("width", 80)),
        )
        tokens: list[dict[str, Any]] = []
        for i in tk.encode(text):
            piece = tk.piece(i)
            try:
                shown: str | None = piece.decode()
            except UnicodeDecodeError:
                shown = None
            tokens.append({"t": shown, "h": piece.hex(), "id": i, "n": len(piece)})
        key = os.environ.get("ANTHROPIC_API_KEY")
        wanted = key and request.get("claude") and text.strip()
        return {
            "text": text,
            "tokens": tokens,
            "count": len(tokens),
            "lines": text.count("\n") + 1,
            "over": over,
            "claude": claude_count(text, key, self.opener) if key and wanted else None,
        }


def handler(app: App) -> type[BaseHTTPRequestHandler]:
    """The request handler serving app."""

    class Handler(BaseHTTPRequestHandler):
        @override
        def log_message(self, format: str, *args: Any) -> None:
            """Quiet: the page polls on every keystroke."""

        def send(self, status: int, body: bytes, kind: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path.startswith("/snippets"):
                self.send(200, json.dumps(app.snippets()).encode(), "application/json")
            else:
                self.send(200, PAGE.read_bytes(), "text/html; charset=utf-8")

        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            try:
                answer = app.tokenize(json.loads(body or b"{}"))
            except ValueError as refused:
                self.send(400, str(refused).encode(), "text/plain; charset=utf-8")
                return
            self.send(200, json.dumps(answer).encode(), "application/json")

    return Handler


def server(app: App, port: int) -> ThreadingHTTPServer:
    """A server for app on 127.0.0.1 at port (0 picks a free one)."""
    return ThreadingHTTPServer(("127.0.0.1", port), handler(app))
