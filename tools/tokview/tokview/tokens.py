"""Tokenizers behind one interface: the ids of a text, and the bytes each id stands for.

tiktoken's o200k_base and cl100k_base are always there. Qwen2.5-Coder and DeepSeek-V3 are
read from their Hugging Face tokenizer.json, only when the `hf` extra (tokenizers) imports;
each file is fetched once into the cache directory.
"""

import importlib.util
import os
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

import tiktoken

HF = {"qwen": "Qwen/Qwen2.5-Coder-7B", "deepseek": "deepseek-ai/DeepSeek-V3"}


@dataclass(frozen=True)
class Tk:
    """One tokenizer: `encode` gives the ids of a text, `piece` the bytes of one id."""

    encode: Callable[[str], list[int]]
    piece: Callable[[int], bytes]

    def pieces(self, text: str) -> list[bytes]:
        """The bytes of each token of text, in order; joined, they are its UTF-8."""
        return [self.piece(i) for i in self.encode(text)]

    def spans(self, text: str) -> list[tuple[int, int]]:
        """[start, end) of each token in the UTF-8 bytes of text; the spans tile them."""
        out: list[tuple[int, int]] = []
        at = 0
        for piece in self.pieces(text):
            out.append((at, at + len(piece)))
            at += len(piece)
        return out


def _byte_chars() -> dict[int, str]:
    """GPT-2's byte-level alphabet: each byte as a printable character. Printable bytes stand
    for themselves; the rest are moved, in order, to U+0100 onwards."""
    kept = [*range(33, 127), *range(161, 173), *range(174, 256)]
    moved = [b for b in range(256) if b not in kept]
    return {b: chr(b) for b in kept} | {b: chr(256 + k) for k, b in enumerate(moved)}


U2B = {char: byte for byte, char in _byte_chars().items()}


def bytes_of(token: str) -> bytes:
    """The bytes a byte-level token stands for. A token outside the alphabet, an added
    special token, stands for its own UTF-8."""
    try:
        return bytes(U2B[char] for char in token)
    except KeyError:
        return token.encode()


def openai(name: str) -> Tk:
    """A tiktoken encoding; special-token text is encoded as ordinary text."""
    enc = tiktoken.get_encoding(name)
    return Tk(lambda text: enc.encode(text, disallowed_special=()), enc.decode_single_token_bytes)


def cache_dir() -> Path:
    """Where fetched tokenizer files live: $XDG_CACHE_HOME/fpl-tokview, else ~/.cache's."""
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "fpl-tokview"


def fetch(url: str, dest: Path) -> None:
    """Dest holds the body of url, written whole or not at all."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(".part")
    with urllib.request.urlopen(url) as response:
        part.write_bytes(response.read())
    part.replace(dest)


def hugging_face(repo: str, get: Callable[[str, Path], None] = fetch) -> Tk:
    """The byte-level BPE of a Hugging Face repository's tokenizer.json, fetched by `get`
    on first use."""
    from tokenizers import Tokenizer  # noqa: PLC0415 -- the hf extra is optional

    path = cache_dir() / repo.replace("/", "_") / "tokenizer.json"
    if not path.exists():
        get(f"https://huggingface.co/{repo}/resolve/main/tokenizer.json", path)
    tok = Tokenizer.from_file(str(path))
    return Tk(
        lambda text: tok.encode(text, add_special_tokens=False).ids,
        lambda i: bytes_of(tok.id_to_token(i) or ""),
    )


def registry() -> dict[str, Callable[[], Tk]]:
    """The tokenizers by the names the page sends; the Hugging Face ones only when the
    tokenizers package imports."""
    names: dict[str, Callable[[], Tk]] = {
        "o200k": partial(openai, "o200k_base"),
        "cl100k": partial(openai, "cl100k_base"),
    }
    if importlib.util.find_spec("tokenizers") is None:
        return names
    return names | {name: partial(hugging_face, repo) for name, repo in HF.items()}


@dataclass
class Tokenizers:
    """The registry's tokenizers, each loaded on first use and kept."""

    loaders: dict[str, Callable[[], Tk]] = field(default_factory=registry)
    loaded: dict[str, Tk] = field(default_factory=dict[str, Tk])

    def get(self, name: str) -> Tk:
        """The tokenizer of that name; a name the registry lacks is a ValueError."""
        if name not in self.loaders:
            raise ValueError(f"unknown tokenizer {name!r}; known: {', '.join(self.loaders)}")
        if name not in self.loaded:
            self.loaded[name] = self.loaders[name]()
        return self.loaded[name]
