"""tokview.tokens: the tokens tile the text's bytes, under every tokenizer."""

import json
import sys
import threading
import time
import urllib.request
from collections.abc import Callable, Generator
from contextlib import contextmanager, suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import pairwise
from pathlib import Path
from typing import Any, override

import pytest
from hypothesis import given
from hypothesis import strategies as st
from tokview import tokens
from tokview.tokens import U2B, Tk, Tokenizers, bytes_of, cache_dir, fetch, hugging_face, registry

LOADED = Tokenizers()
SPECIAL = "<| |>"  # a space is outside the byte-level alphabet


def tiny_tokenizer(path: Path) -> None:
    """A byte-level BPE over the 256 byte characters, two merges, and an added special token."""
    vocab = dict(U2B) | {"du": 256, "dup": 257, "Ġt": 258}
    spec = {
        "version": "1.0",
        "truncation": None,
        "padding": None,
        "added_tokens": [
            {
                "id": 259,
                "content": SPECIAL,
                "single_word": False,
                "lstrip": False,
                "rstrip": False,
                "normalized": False,
                "special": True,
            }
        ],
        "normalizer": None,
        "pre_tokenizer": {
            "type": "ByteLevel",
            "add_prefix_space": False,
            "trim_offsets": True,
            "use_regex": True,
        },
        "post_processor": None,
        "decoder": None,
        "model": {
            "type": "BPE",
            "dropout": None,
            "unk_token": None,
            "continuing_subword_prefix": None,
            "end_of_word_suffix": None,
            "fuse_unk": False,
            "byte_fallback": False,
            "vocab": vocab,
            "merges": ["d u", "du p", "Ġ t"],
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec))


def tiles(tk: Tk, text: str) -> None:
    pieces = tk.pieces(text)
    assert b"".join(pieces) == text.encode()
    spans = tk.spans(text)
    assert [end - start for start, end in spans] == [len(p) for p in pieces]
    assert all(a[1] == b[0] for a, b in pairwise(spans))


@given(st.text())
def test_o200k_tiles_the_bytes(text: str) -> None:
    tiles(LOADED.get("o200k"), text)


@given(st.text())
def test_cl100k_tiles_the_bytes(text: str) -> None:
    tiles(LOADED.get("cl100k"), text)


def test_special_token_text_is_ordinary_text() -> None:
    tiles(LOADED.get("o200k"), "<|endoftext|>")


def test_the_byte_map_is_a_bijection_onto_printable_characters() -> None:
    assert sorted(U2B.values()) == list(range(256))
    assert all(c.isprintable() and not c.isspace() for c in U2B)
    assert {chr(b): b for b in range(33, 127)}.items() <= U2B.items()
    assert U2B["Ġ"] == ord(" ")
    assert U2B["Ċ"] == ord("\n")


def test_a_token_outside_the_alphabet_is_its_own_utf8() -> None:
    assert bytes_of("ĠtimesĊ") == b" times\n"
    assert bytes_of(SPECIAL) == SPECIAL.encode()


def test_an_unknown_name_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown tokenizer 'gpt2'"):
        Tokenizers().get("gpt2")


def test_a_tokenizer_loads_once() -> None:
    calls: list[str] = []
    tk = Tk(lambda _: [], lambda _: b"")

    def load() -> Tk:
        calls.append("load")
        return tk

    loaded = Tokenizers({"t": load})
    assert loaded.get("t") is loaded.get("t") is tk
    assert calls == ["load"]


class Watched:
    """A lock that sets contended when a caller arrives while another holds it."""

    def __init__(self) -> None:
        self.inner = threading.Lock()
        self.contended = threading.Event()

    def __enter__(self) -> None:
        if self.inner.locked():
            self.contended.set()
        self.inner.acquire()

    def __exit__(self, *_: object) -> None:
        self.inner.release()


def test_concurrent_first_uses_load_once() -> None:
    calls: list[str] = []
    tk = Tk(lambda _: [], lambda _: b"")
    entered, release = threading.Event(), threading.Event()

    def held() -> Tk:
        calls.append("load")
        entered.set()
        release.wait(5)
        return tk

    lock = Watched()
    loaded = Tokenizers({"t": held}, lock=lock)
    got: list[Tk] = []
    first, second = (threading.Thread(target=lambda: got.append(loaded.get("t"))) for _ in "12")
    first.start()
    assert entered.wait(5)
    second.start()
    assert lock.contended.wait(5)  # the second caller is at the lock while the load holds it
    assert got == []
    release.set()
    first.join()
    second.join()
    assert calls == ["load"]
    assert got == [tk, tk]


def test_the_hugging_face_entries_need_tokenizers(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("tokenizers")
    assert set(registry()) == {"o200k", "cl100k", "qwen", "deepseek"}
    monkeypatch.setitem(sys.modules, "tokenizers", None)
    assert set(registry()) == {"o200k", "cl100k"}


def test_the_cache_follows_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert cache_dir() == tmp_path / "fpl-tokview"
    monkeypatch.delenv("XDG_CACHE_HOME")
    assert cache_dir() == Path.home() / ".cache" / "fpl-tokview"


def test_fetch_writes_the_body_whole(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_text("{}")
    dest = tmp_path / "a" / "b" / "tokenizer.json"
    fetch(source.as_uri(), dest)
    assert dest.read_text() == "{}"
    assert not dest.with_suffix(".part").exists()


@contextmanager
def serving(answer: Callable[[BaseHTTPRequestHandler, threading.Event], None]) -> Generator[str]:
    """The URL of a local server that answers each GET with answer, for the length of the
    block; answer is handed an event set when the block ends, to stop waiting on."""
    done = threading.Event()

    class Answer(BaseHTTPRequestHandler):
        @override
        def log_message(self, format: str, *args: Any) -> None:
            """Quiet."""

        def do_GET(self) -> None:
            with suppress(OSError):  # the client gave up first, as the tests want it to
                answer(self, done)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Answer)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}/tokenizer.json"
    finally:
        done.set()
        httpd.shutdown()
        httpd.server_close()


def head(handler: BaseHTTPRequestHandler, length: int) -> None:
    """A 200 whose body will be length bytes, its headers sent."""
    handler.send_response(200)
    handler.send_header("Content-Length", str(length))
    handler.end_headers()


def silent(handler: BaseHTTPRequestHandler, done: threading.Event) -> None:
    """Promises a byte and never sends it."""
    head(handler, 1)
    done.wait()


def trickling(handler: BaseHTTPRequestHandler, done: threading.Event) -> None:
    """A byte every 20 ms, never silent for long, two seconds in all."""
    head(handler, 100)
    for _ in range(100):
        handler.wfile.write(b" ")
        if done.wait(0.02):
            return


def dripping(head: bytes) -> Callable[[BaseHTTPRequestHandler, threading.Event], None]:
    """Sends head a byte every 20 ms, and nothing after it."""

    def answer(handler: BaseHTTPRequestHandler, done: threading.Event) -> None:
        for byte in head:
            handler.wfile.write(bytes([byte]))
            if done.wait(0.02):
                return

    return answer


def eleven(handler: BaseHTTPRequestHandler, _: threading.Event) -> None:
    """Eleven bytes at once."""
    head(handler, 11)
    handler.wfile.write(b"x" * 11)


def test_fetch_gives_up_on_a_silent_server(tmp_path: Path) -> None:
    with serving(silent) as url:
        start = time.monotonic()
        with pytest.raises(TimeoutError):
            fetch(url, tmp_path / "tokenizer.json", timeout=0.2)
        assert time.monotonic() - start < 2
    assert not any(tmp_path.iterdir())


def test_fetch_gives_up_on_a_server_that_trickles(tmp_path: Path) -> None:
    with serving(trickling) as url:
        start = time.monotonic()
        with pytest.raises(TimeoutError, match=r"longer than 0\.3 s"):
            fetch(url, tmp_path / "tokenizer.json", timeout=5, deadline=0.3)
        assert time.monotonic() - start < 1.5
    assert not any(tmp_path.iterdir())


@pytest.mark.parametrize(
    "head",
    # Cut anywhere, the first is no status line at all (its code is zero however long)
    # and the second a whole one, its headers ended early.
    [b"HTTP/1.0 0".ljust(100, b"0"), b"HTTP/1.0 200 OK\r\nX-Slow: ".ljust(100, b"a")],
    ids=["status line", "headers"],
)
def test_fetch_gives_up_on_a_server_that_trickles_its_head(tmp_path: Path, head: bytes) -> None:
    with serving(dripping(head)) as url:
        start = time.monotonic()
        with pytest.raises(TimeoutError, match=r"longer than 0\.3 s"):
            fetch(url, tmp_path / "tokenizer.json", timeout=5, deadline=0.3)
        assert time.monotonic() - start < 1.5
    assert not any(tmp_path.iterdir())


def test_fetch_refuses_a_body_over_the_limit(tmp_path: Path) -> None:
    dest = tmp_path / "tokenizer.json"
    with serving(eleven) as url:
        with pytest.raises(OSError, match="larger than 10 bytes"):
            fetch(url, dest, limit=10)
        assert not any(tmp_path.iterdir())
        fetch(url, dest, limit=11)
    assert dest.read_bytes() == b"x" * 11


def test_a_cut_after_the_head_leaves_the_body_alone() -> None:
    cutter = tokens.Cutter()
    with serving(eleven) as url, urllib.request.build_opener(cutter).open(url) as response:
        cutter.cut()
        assert response.read() == b"x" * 11
    assert len(cutter.conns) == 1


def test_the_fetch_bounds_clear_the_real_files() -> None:
    assert 0 < tokens.TIMEOUT <= tokens.DEADLINE < 3600
    assert tokens.LIMIT >= 32 << 20  # DeepSeek-V3's tokenizer.json is under 8 MiB


@pytest.fixture
def hf(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Tk:
    """The tiny tokenizer, loaded the way a Hugging Face one is, fetched once. Skipped
    without the hf extra; `make tools` syncs every extra, so the lane always runs it."""
    pytest.importorskip("tokenizers")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    urls: list[str] = []

    def get(url: str, dest: Path) -> None:
        urls.append(url)
        tiny_tokenizer(dest)

    tk = hugging_face("org/tiny", get)
    hugging_face("org/tiny", get)
    assert urls == ["https://huggingface.co/org/tiny/resolve/main/tokenizer.json"]
    return tk


def test_hugging_face_tiles_the_bytes(hf: Tk) -> None:
    for text in ["sq : x -- y\t; the square", "naïve π \u2250 \u2228 😀", SPECIAL + " x", ""]:
        tiles(hf, text)
    assert SPECIAL.encode() in hf.pieces(SPECIAL)
    assert b"dup" in hf.pieces("\tdup times")


def test_the_registry_names_its_repositories() -> None:
    assert tokens.HF == {"qwen": "Qwen/Qwen2.5-Coder-7B", "deepseek": "deepseek-ai/DeepSeek-V3"}
