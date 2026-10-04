"""Tokenizers behind one interface: the ids of a text, and the bytes each id stands for.

tiktoken's o200k_base and cl100k_base are always there. Qwen2.5-Coder and DeepSeek-V3 are
read from their Hugging Face tokenizer.json, only when the `hf` extra (tokenizers) imports;
each file is fetched once into the cache directory.
"""

import importlib.util
import os
import threading
import time
import urllib.request
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

import tiktoken

HF = {"qwen": "Qwen/Qwen2.5-Coder-7B", "deepseek": "deepseek-ai/DeepSeek-V3"}
TIMEOUT = 60.0  # seconds a download may stay silent before it is given up
DEADLINE = 300.0  # seconds a download may run in all, however steadily its bytes come
LIMIT = 64 << 20  # bytes of a tokenizer.json; the real ones are under 8 MiB
CHUNK = 1 << 16  # bytes read, at most, before the deadline is checked again


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


def fetch(
    url: str,
    dest: Path,
    *,
    timeout: float = TIMEOUT,
    deadline: float = DEADLINE,
    limit: int = LIMIT,
) -> None:
    """Dest holds the body of url, written whole or not at all.

    A server silent for timeout seconds, a download still running after deadline seconds,
    and a body over limit bytes are each an OSError, never a request that hangs or a disk
    that fills; the fetch runs under the Tokenizers lock, so every other first use waits
    on it. A socket timeout alone bounds each read, not the whole: a server that sends a
    byte at a time would never trip it. So the body is read as it arrives (read1 returns
    what one read gave, where read(n) would wait for all n bytes) and the clock checked
    after each piece; a download overruns its deadline by at most one timeout."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(".part")
    end = time.monotonic() + deadline
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response, part.open("wb") as out:
            size = 0
            while chunk := response.read1(CHUNK):
                size += len(chunk)
                if size > limit:
                    raise OSError(f"{url} is larger than {limit} bytes")
                if time.monotonic() > end:
                    raise TimeoutError(f"{url} took longer than {deadline} s")
                out.write(chunk)
    except OSError:
        part.unlink(missing_ok=True)
        raise
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
    """The registry's tokenizers, each loaded on first use and kept. The server answers
    requests on threads, so loading holds a lock: two first requests for one Hugging Face
    tokenizer would otherwise both fetch it through the same `.part` file. The lock is
    anything held with `with`, so a test can watch who waits on it."""

    loaders: dict[str, Callable[[], Tk]] = field(default_factory=registry)
    loaded: dict[str, Tk] = field(default_factory=dict[str, Tk])
    lock: AbstractContextManager[object] = field(
        default_factory=threading.Lock, repr=False, compare=False
    )

    def get(self, name: str) -> Tk:
        """The tokenizer of that name; a name the registry lacks is a ValueError."""
        if name not in self.loaders:
            raise ValueError(f"unknown tokenizer {name!r}; known: {', '.join(self.loaders)}")
        with self.lock:
            if name not in self.loaded:
                self.loaded[name] = self.loaders[name]()
            return self.loaded[name]
