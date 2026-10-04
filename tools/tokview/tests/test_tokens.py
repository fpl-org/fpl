"""tokview.tokens: the tokens tile the text's bytes, under every tokenizer."""

import json
import sys
import threading
import urllib.request
from itertools import pairwise
from pathlib import Path

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


def test_concurrent_first_uses_load_once() -> None:
    calls: list[str] = []
    tk = Tk(lambda _: [], lambda _: b"")

    def slow() -> Tk:
        calls.append("load")
        threading.Event().wait(0.2)  # long enough for the other request to arrive
        return tk

    loaded = Tokenizers({"t": slow})
    got: list[Tk] = []
    threads = [threading.Thread(target=lambda: got.append(loaded.get("t"))) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
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


def test_fetch_gives_up_in_finite_time(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    timeouts: list[object] = []
    urlopen = urllib.request.urlopen

    def recording(url: str, *, timeout: float) -> object:
        timeouts.append(timeout)
        return urlopen(url, timeout=timeout)

    monkeypatch.setattr(urllib.request, "urlopen", recording)
    source = tmp_path / "source.json"
    source.write_text("{}")
    fetch(source.as_uri(), tmp_path / "tokenizer.json")
    assert timeouts == [tokens.TIMEOUT]
    assert 0 < tokens.TIMEOUT < 600


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
