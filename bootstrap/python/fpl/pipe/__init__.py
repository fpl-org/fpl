"""
# Pipe

`fonify` is the whole trip to the wire. `source` only fonifies. `render`
only defonifies.
"""

import sys
from decimal import Decimal

from fpl.arrow import Pass
from fpl.errors import FplError
from fpl.fon import Dict, List, Num, Str, Tagged, read, write
from fpl.lex import Prelexed, Stashed, Tokens, lex
from fpl.parse import parse

stdio = Pass("stdio", lambda stage: stage)


def _text(value: object) -> str:
    if not isinstance(value, Str):
        raise FplError(
            __import__("fpl.errors", fromlist=["Span"]).Span(1, 1),
            "expected text",
        )
    return value.text


def fonify_text(text: str) -> bytes:
    """
    A → bytes. Raw quotes when the text allows them.
    """
    raw = "「" not in text and "」" not in text
    return (write(Str(text, raw)) + "\n").encode()


def defonify_text(data: bytes) -> str:
    got = read(data.decode())
    if not isinstance(got, Str):
        raise ValueError("expected a FON string")
    return got.text


def _num(value: int) -> Num:
    return Num(Decimal(value))


def fonify_tokens(tokens: Tokens) -> bytes:
    stash = tuple(
        Tagged(
            (
                _num(key),
                _num(item.start),
                _num(item.end),
                Str(item.kind, raw=True),
                _num(item.depth),
            )
        )
        for key, item in tokens.lexed.stash.items()
    )
    raw = tuple(
        Tagged((_text_sym(kind), Str(value, raw=True), _num(start), _num(end)))
        for kind, value, start, end in tokens.raw
    )
    document = Dict(
        (
            (Str("source", raw=True), Str(tokens.source, raw=True)),
            (Str("code", raw=True), Str(tokens.lexed.code, raw=True)),
            (
                Str("origin", raw=True),
                List(tuple(_num(n) for n in tokens.lexed.origin)),
            ),
            (Str("stash", raw=True), List(stash)),
            (Str("tokens", raw=True), List(raw)),
        )
    )
    return (write(document) + "\n").encode()


def _text_sym(kind: str) -> Str:
    return Str(kind, raw=True)


def _pair(item: object) -> tuple:
    if not isinstance(item, Tagged):
        raise ValueError("expected a tagged tuple")
    return item.items


def defonify_tokens(data: bytes) -> Tokens:
    got = read(data.decode())
    if not isinstance(got, Dict):
        raise ValueError("expected a FON dict")
    fields = {
        key.text: value for key, value in got.entries if isinstance(key, Str)
    }
    origin = fields["origin"]
    stash = fields["stash"]
    raw = fields["tokens"]
    if (
        not isinstance(origin, List)
        or not isinstance(stash, List)
        or not isinstance(raw, List)
    ):
        raise ValueError("malformed tokens")
    held: dict[int, Stashed] = {}
    for item in stash.items:
        key, start, end, kind, depth = _pair(item)
        held[int(key.value)] = Stashed(
            kind.text, int(start.value), int(end.value), int(depth.value)
        )
    lexed = Prelexed(
        _text(fields["code"]), tuple(int(n.value) for n in origin.items), held
    )
    packed = tuple(
        (kind.text, value.text, int(start.value), int(end.value))
        for kind, value, start, end in (_pair(item) for item in raw.items)
    )
    return Tokens(_text(fields["source"]), lexed, packed)


def cli(stage: object) -> int:
    """
    Read stdin, run one stage, write stdout. A Pass or its name both
    work.
    """
    name = stage if isinstance(stage, str) else stage.name
    data = sys.stdin.buffer.read()
    try:
        sys.stdout.buffer.write(_run(name, data))
    except (FplError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


def _run(name: str, data: bytes) -> bytes:
    if name == "source":
        return fonify_text(data.decode())
    if name == "render":
        return defonify_text(data).encode()
    if name == "lex":
        return fonify_tokens(lex(defonify_text(data)))
    text = defonify_text(data) if name != "parse" else ""
    if name == "parse":
        program = parse(defonify_tokens(data))
        from fpl.print import render

        return fonify_text(render(program))
    from fpl.desugar import desugar
    from fpl.elaborate import elaborate
    from fpl.lex import lex as lex_pass
    from fpl.parse import parse as parse_pass

    program = parse_pass(lex_pass(text))
    if name == "desugar":
        desugar(program)
        from fpl.print import render

        return fonify_text(render(program))
    statements = desugar(program)
    if name == "elaborate":
        elaborate(statements)
        from fpl.print import render

        return fonify_text(render(program))
    if name == "eval":
        from fpl.desugar import listing
        from fpl.evaluate import evaluate
        from fpl.print import render

        return fonify_text(render(listing(evaluate(elaborate(statements)))))
    raise ValueError(f"unknown stage {name}")
