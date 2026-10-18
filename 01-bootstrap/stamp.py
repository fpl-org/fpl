"""
Write the vault pages. Signature pages come from a table. Filled pages
embed the seed.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
SEED = ROOT / "fpl"
PARTS = (
    ("boundary", ("source", "fon", "pipe", "render")),
    (
        "pass",
        (
            "lex",
            "parse",
            "resolve",
            "expand",
            "desugar",
            "elaborate",
            "lower",
            "normalize",
            "optimize",
            "evaluate",
            "codegen",
        ),
    ),
    (
        "repr",
        (
            "source",
            "tokens",
            "syntax",
            "resolved",
            "expanded",
            "elaborated",
            "core",
        ),
    ),
    ("compose", ("pass", "run", "inspect", "build")),
    ("labs", ("pipeline",)),
    ("nagini", ("advance",)),
)


def _part(name: str) -> tuple[int, tuple[str, ...]]:
    for index, (part, names) in enumerate(PARTS, 1):
        if part == name:
            return index, names
    raise KeyError(name)


def part_dir(name: str) -> str:
    index, _ = _part(name)
    return f"01.{index:02d}-{name}"


def note(part: str, name: str) -> str:
    index, names = _part(part)
    return f"01.{index:02d}.{names.index(name) + 1:02d}-{name}.md"


MARIMO_VERSION = "0.23.10"

FRONT = (
    """---
type: {type}
title: {title}
description: {description}
tags:
  - {tag}
engine: marimo
marimo-version: """
    + MARIMO_VERSION
    + """
width: full
---

```python {{.marimo name="setup"}}
import marimo as mo
```

# {heading}

{body}
"""
)


def heading(path: Path, title: str) -> str:
    addr, sep, _ = path.stem.partition("-")
    if sep and addr[:1].isdigit() and not title.startswith(addr):
        return f"{addr} {title}"
    return title


def page(
    path: Path, type_: str, title: str, description: str, body: str, tag: str
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    shown = heading(path, title)
    path.write_text(
        FRONT.format(
            type=type_,
            title=shown,
            heading=shown,
            description=description,
            body=body,
            tag=tag,
        )
    )


def cell(name: str, source: str) -> str:
    return f'```python {{.marimo name="{name}"}}\n{source.rstrip()}\n```\n'


def signature() -> None:
    """
    Pages with an arrow and no Python.
    """
    passes = [
        (
            "resolve",
            "Resolve",
            "Binders become identities.",
            "Syntax → Resolved",
            "parse",
            "expand",
        ),
        (
            "expand",
            "Expand",
            "Sugar dies here. The term stays on the surface.",
            "Resolved → Expanded",
            "resolve",
            "elaborate",
        ),
        (
            "lower",
            "Lower",
            "Reify the elaborated term into the dependent-CBPV core.",
            "Elaborated → Core",
            "elaborate",
            "normalize",
        ),
        (
            "normalize",
            "Normalize",
            "A pass over the dependent-CBPV core.",
            "Core → Core",
            "lower",
            "optimize",
        ),
        (
            "optimize",
            "Optimize",
            "A pass over the dependent-CBPV core.",
            "Core → Core",
            "normalize",
            "codegen",
        ),
        (
            "codegen",
            "Codegen",
            "The core becomes the target.",
            "Core → Target",
            "optimize",
            "evaluate",
        ),
    ]
    for name, title, description, arrow, prev, nxt in passes:
        body = (
            f"`{arrow}`\n\n"
            f"[{prev}]({note('pass', prev)}) is the previous arrow. "
            f"[{nxt}]({note('pass', nxt)}) is the next.\n\n"
            'This page is the signature. The walker does not have this pass on'
            'its own yet.'
        )
        page(
            ROOT / part_dir("pass") / note("pass", name),
            "Pass",
            title,
            description,
            body,
            "pass",
        )
    reprs = [
        (
            "source",
            "Source",
            "The program text, after the ingress and before lex.",
        ),
        (
            "tokens",
            "Tokens",
            'What the lexer Lark yields. The parser Lark reads these and does'
            'not lex again.',
        ),
        ("syntax", "Syntax", "The surface ABT."),
        ("resolved", "Resolved", "Binders are identities."),
        ("expanded", "Expanded", "Sugar is gone. The term is still surface."),
        (
            "elaborated",
            "Elaborated",
            'Polarity, effects, and metavariables are known. Still'
            'surface-adjacent.',
        ),
        (
            "core",
            "Core",
            'The dependent-CBPV core. It later splits into Core.Value and'
            'Core.Comp. This trial keeps one sort.',
        ),
    ]
    for name, title, description in reprs:
        page(
            ROOT / part_dir("repr") / note("repr", name),
            "Repr",
            title,
            description,
            description + "\n",
            "repr",
        )
    page(
        ROOT / part_dir("compose") / note("compose", "build"),
        "Composition",
        "Build",
        "The release chain, a program that orders passes.",
        '``` build = lex >> parse >> resolve >> expand >> elaborate >> lower'
        '>> optimize >> codegen ```'
        "A `>>` chain orders passes. It is not the semantics.\n",
        "composition",
    )
    page(
        ROOT / part_dir("compose") / note("compose", "inspect"),
        "Composition",
        "Inspect",
        "Stop once elaboration has established what the core needs.",
        "```\ninspect = lex >> parse >> resolve >> expand >> "
        "elaborate\n```\n\n"
        'Elaboration establishes the semantic information. Lowering reifies'
        'it.',
        "composition",
    )


def indexes() -> None:
    def listing(folder: str, names: list[str]) -> str:
        return (
            "\n".join(f"- [{name}]({note(folder, name)})" for name in names)
            + "\n"
        )

    for name in ("pass", "repr", "compose", "boundary", "labs", "nagini"):
        (ROOT / part_dir(name)).mkdir(exist_ok=True)
    (ROOT / part_dir("pass") / "index.md").write_text(
        "# Passes\n\n"
        + listing(
            "pass",
            [
                "lex",
                "parse",
                "resolve",
                "expand",
                "desugar",
                "elaborate",
                "lower",
                "normalize",
                "optimize",
                "evaluate",
                "codegen",
            ],
        )
    )
    (ROOT / part_dir("repr") / "index.md").write_text(
        "# Representations\n\n"
        + listing(
            "repr",
            [
                "source",
                "tokens",
                "syntax",
                "resolved",
                "expanded",
                "elaborated",
                "core",
            ],
        )
    )
    (ROOT / part_dir("compose") / "index.md").write_text(
        "# Compositions\n\n"
        + listing("compose", ["pass", "run", "build", "inspect"])
    )
    (ROOT / part_dir("boundary") / "index.md").write_text(
        "# Boundary\n\n"
        + listing("boundary", ["source", "fon", "pipe", "render"])
    )
    (ROOT / "index.md").write_text(
        "---\n"
        'okf_version: "0.2"\n'
        "---\n\n"
        "# FPL bootstrap\n\n"
        'The walker as a composition of passes. Inside one process the values'
        'are ABTs.'
        "FON is only the wire.\n\n"
        "## Passes\n\n"
        "- [01.02.01-lex](01.02-pass/01.02.01-lex.md)\n"
        "- [01.02.02-parse](01.02-pass/01.02.02-parse.md)\n"
        "- [01.02.05-desugar](01.02-pass/01.02.05-desugar.md)\n"
        "- [01.02.06-elaborate](01.02-pass/01.02.06-elaborate.md)\n"
        "- [01.02.10-evaluate](01.02-pass/01.02.10-evaluate.md)\n\n"
        "## Boundary\n\n"
        "- [01.01.01-source](01.01-boundary/01.01.01-source.md)\n"
        "- [01.01.03-pipe](01.01-boundary/01.01.03-pipe.md)\n"
        "- [01.01.04-render](01.01-boundary/01.01.04-render.md)\n"
    )
    (ROOT / "log.md").write_text(
        "# Log\n\n"
        "The literate trial of the bootstrap. The seed walker is unchanged.\n"
    )
    (ROOT / part_dir("labs") / note("labs", "pipeline")).write_text(
        "---\n"
        "type: Lab\n"
        "title: Pipeline\n"
        "description: The in-process chain beside the shell pipe.\n"
        "tags:\n"
        "  - lab\n"
        "engine: marimo\n"
        f"marimo-version: {MARIMO_VERSION}\n"
        "---\n\n"
        '```python {.marimo name="setup"}\n'
        "import marimo as mo\n"
        "```\n\n"
        "# Pipeline\n\n"
        'One cell is the in-process chain. The other is the same passes across'
        'FON.'
        + cell(
            "run",
            "import fpl\n\n"
            'run_now = fpl.lex >> fpl.parse >> fpl.desugar >> fpl.elaborate >>'
            'fpl.evaluate'
            "run_now\n",
        )
    )


def wrap(name: str, source: str, tail: str) -> str:
    return source.rstrip() + "\n\n" + tail.strip() + "\n"


LEX_TAIL = '''
from pathlib import Path

from lark import Lark

from fpl.arrow import Pass

GRAMMAR = Path(__file__).resolve().parents[1] / "grammar.lark"


@dataclass(frozen=True)
class Tokens:
    "The lexer's output: the pre-lexed text and the tokens the second Lark"
    'will read.'

    source: str
    lexed: Prelexed
    raw: tuple[tuple[str, str, int, int], ...]


_LEXER: Lark | None = None


def token_lark() -> Lark:
    """The lexer Lark. It does not parse."""
    global _LEXER
    if _LEXER is None:
        _LEXER = Lark(
            GRAMMAR.read_text(),
            parser="lalr",
            propagate_positions=True,
            maybe_placeholders=False,
        )
    return _LEXER


def code_tokens(code: str) -> list:
    """Tokens for code the pre-lexer already produced."""
    return list(token_lark().lex(code))


def _pack(got: list) -> tuple[tuple[str, str, int, int], ...]:
    return tuple(
        (token.type, str(token), token.start_pos or 0,
        token.end_pos or 0) for token in got
    )


def _lex(source: str) -> Tokens:
    lexed = prelex(source)
    return Tokens(source, lexed, _pack(code_tokens(lexed.code)))


lex = Pass("lex", _lex)
'''


def filled() -> None:
    lex_src = (SEED / "lex.py").read_text()
    page(
        ROOT / part_dir("pass") / note("pass", "lex"),
        "Pass",
        "Lex",
        'One Lark. Source in, tokens out. The hand counter stays inside this'
        'stage.',
        "The hand counter in the seed's `lex.py` counts pairs and tabs,"
        'because a grammar cannot.'
        "Then a Lark lexer, and nothing else, yields the tokens.\n\n"
        "[01.02.02-parse](01.02.02-parse.md) reads those tokens with a second Lark.\n\n"
        + cell("lex", wrap("lex", lex_src, LEX_TAIL)),
        "pass",
    )
    body = (SEED / "desugar.py").read_text()
    page(
        ROOT / part_dir("pass") / note("pass", "desugar"),
        "Pass",
        "Desugar",
        "The walker's fuse of resolve, expand, and lower. Not the type of"
        'expand.',
        'Today this is `Syntax → Core`. [01.02.03-resolve](01.02.03-resolve.md),'
        '[01.02.04-expand](01.02.04-expand.md), and'
        "[01.02.07-lower](01.02.07-lower.md) are the arrows it stands in for.\n\n"
        + cell(
            "desugar",
            wrap(
                "desugar",
                "from fpl.arrow import Pass\n\n" + body,
                "_desugar_fn = desugar\n"
                'desugar = Pass("desugar", _desugar_fn)\n',
            ),
        ),
        "pass",
    )
    body = (SEED / "types.py").read_text()
    page(
        ROOT / part_dir("pass") / note("pass", "elaborate"),
        "Pass",
        "Elaborate",
        'Establish polarity, effects, and metavariables. The term stays'
        'surface-adjacent.',
        '[01.02.05-desugar](01.02.05-desugar.md) feeds this. [01.02.07-lower](01.02.07-lower.md) is what'
        'reifies the core, and the walker has not split that out yet.'
        + cell(
            "elaborate",
            wrap(
                "elaborate",
                "from fpl.arrow import Pass\n\n" + body,
                "def _checked(statements):\n"
                "    _elaborate_fn(statements)\n"
                "    return statements\n\n\n"
                "_elaborate_fn = elaborate\n"
                'elaborate = Pass("elaborate", _checked)\n',
            ),
        ),
        "pass",
    )
    body = (SEED / "eval.py").read_text()
    page(
        ROOT / part_dir("pass") / note("pass", "evaluate"),
        "Pass",
        "Evaluate",
        'Core statements to the stacks each run line leaves. Fuel is the'
        "walker's bound.",
        'The environment rides inside the call. This wrapper closes over the'
        "walker's fuel."
        + cell(
            "evaluate",
            wrap(
                "evaluate",
                "from fpl.arrow import Pass\n\n" + body,
                "def _run(statements):\n"
                "    return _eval_fn(statements, 1_000_000)\n\n\n"
                "_eval_fn = evaluate\n"
                'evaluate = Pass("eval", _run)\n',
            ),
        ),
        "pass",
    )
    body = (SEED / "fon.py").read_text()
    page(
        ROOT / part_dir("boundary") / note("boundary", "fon"),
        "Pass",
        "FON",
        "The inert codec. It reads and writes data. It does not elaborate.",
        "This is the seed's FON reader and writer.\n\n"
        + cell(
            "fon",
            "from fpl.arrow import Pass\n\n"
            + body
            + '\nfon = Pass("fon", read)\n',
        ),
        "boundary",
    )


def hand() -> None:
    page(
        ROOT / part_dir("compose") / note("compose", "pass"),
        "Composition",
        "Pass",
        "A pass is one object. >> composes two of them.",
        'Python has no pipe operator. `>>` on a Pass is composition. On an int'
        'it stays a shift.'
        + cell(
            "pass",
            '''
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Pass[A, B]:
    """One arrow. Calling it runs the function. >> builds the next arrow."""

    name: str
    fn: Callable[[A], B]

    def __call__(self, value: A) -> B:
        return self.fn(value)

    def __rshift__[C](self, nxt: Pass[B, C]) -> Pass[A, C]:
        return Pass(f"{self.name}>>{nxt.name}", lambda value: nxt(self(value)))
'''.lstrip(),
        ),
        "composition",
    )
    page(
        ROOT / part_dir("compose") / note("compose", "run"),
        "Composition",
        "Run",
        "The walker's prefix, in-process.",
        '``` run = lex >> parse >> resolve >> expand >> elaborate >> lower >>'
        'evaluate ```'
        'The executable chain is the prefix the walker actually runs.'
        '`desugar` stands in for'
        "resolve, expand, and lower.\n\n"
        + cell(
            "run",
            r'''
from fpl.ast_core import Run
from fpl.desugar import desugar, listing
from fpl.elaborate import elaborate
from fpl.errors import FplError
from fpl.evaluate import evaluate
from fpl.lex import lex
from fpl.parse import parse
from fpl.print import render

run_now = lex >> parse >> desugar >> elaborate >> evaluate

INDENT_COLUMNS = 4


def _notebook_indent(source: str) -> str:
    """Turn leading spaces into tabs for notebook editors that indent with
    spaces.

    Uses ceiling division by INDENT_COLUMNS so two spaces still become one
    tab."""
    lines: list[str] = []
    for line in source.split("\n"):
        n = 0
        while n < len(line) and line[n] == " ":
            n += 1
        if n == 0:
            lines.append(line)
            continue
        levels = (n + INDENT_COLUMNS - 1) // INDENT_COLUMNS
        lines.append("\t" * levels + line[n:])
    return "\n".join(lines)


def _run(source: str, session: str) -> str:
    """Render one program. `session` is accepted and not stored."""
    del session
    return render(listing(run_now(_notebook_indent(source))))


class Session:
    """A named run. The name is kept and not stored beyond the object."""

    def __init__(self, name: str) -> None:
        self.name = name

    def file(self, path: str) -> str:
        """Read a file as UTF-8 and render it."""
        source = open(path, encoding="utf-8").read()
        return _run(source, self.name)

    def src(self, source: str) -> str:
        """Render a source string."""
        return _run(source, self.name)


default = Session("default")


def run_file(path: str) -> int:
    """Run one file the way the seed walker does. Goals go to stderr."""
    try:
        text = default.file(path)
    except FplError as error:
        print(error)
        return 1
    print(text, end="")
    return 0
'''.lstrip(),
        ),
        "composition",
    )
    page(
        ROOT / part_dir("boundary") / note("boundary", "pipe"),
        "Pass",
        "Pipe",
        "defonify >> stage >> fonify, except at the two ends.",
        '`fonify` is the whole trip to the wire. `source` only fonifies.'
        '`render` only defonifies.'
        + cell("pipe", PIPE),
        "boundary",
    )
    page(
        ROOT / part_dir("boundary") / note("boundary", "source"),
        "Pass",
        "Source",
        "Bytes in, FON out. Not a compiler pass.",
        "The pipe does not start on FON. This is the ingress.\n\n"
        + cell(
            "source",
            """
import sys

from fpl.pipe import cli


def main() -> None:
    sys.exit(cli("source"))


if __name__ == "__main__":
    main()
""".lstrip(),
        ),
        "boundary",
    )
    page(
        ROOT / part_dir("boundary") / note("boundary", "render"),
        "Pass",
        "Render",
        "FON in, text out. Not a compiler pass.",
        "The pipe ends in text a person can read.\n\n"
        + cell(
            "render",
            """
import sys

from fpl.pipe import cli


def main() -> None:
    sys.exit(cli("render"))


if __name__ == "__main__":
    main()
""".lstrip(),
        ),
        "boundary",
    )
    (ROOT / part_dir("nagini")).mkdir(exist_ok=True)
    (ROOT / part_dir("nagini") / note("nagini", "advance")).write_text(
        "---\n"
        "type: Pass\n"
        "title: Advance\n"
        "description: One pure function on a frozen node, for Nagini.\n"
        "tags:\n"
        "  - pass\n"
        "engine: marimo\n"
        f"marimo-version: {MARIMO_VERSION}\n"
        "---\n\n"
        '```python {.marimo name="setup"}\n'
        "import marimo as mo\n"
        "```\n\n"
        "# Advance\n\n"
        'Nagini checks this. It does not call Lark, and it does not override a'
        'dunder.'
        + cell(
            "advance",
            '''
from dataclasses import dataclass

from nagini_contracts.contracts import Ensures, Requires, Result


@dataclass(frozen=True)
class Span:
    """A source position. Nagini sees this. The parser does not live here."""

    line: int
    col: int


def column(span: Span) -> int:
    """The column, unchanged. The contracts are the whole proof."""
    Requires(span.line >= 1)
    Requires(span.col >= 1)
    Ensures(Result() == span.col)
    return span.col
'''.lstrip(),
        )
    )


PIPE = r'''
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
        raise FplError(__import__("fpl.errors", fromlist=["Span"]).Span(1,
        1), "expected text")
    return value.text


def fonify_text(text: str) -> bytes:
    """A → bytes. Raw quotes when the text allows them."""
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
        Tagged((
            _num(key),
            _num(item.start),
            _num(item.end),
            Str(item.kind, raw=True),
            _num(item.depth),
        ))
        for key, item in tokens.lexed.stash.items()
    )
    raw = tuple(
        Tagged((_text_sym(kind), Str(value, raw=True), _num(start), _num(end)))
        for kind, value, start, end in tokens.raw
    )
    document = Dict((
        (Str("source", raw=True), Str(tokens.source, raw=True)),
        (Str("code", raw=True), Str(tokens.lexed.code, raw=True)),
        (Str("origin", raw=True),
        List(tuple(_num(n) for n in tokens.lexed.origin))),
        (Str("stash", raw=True), List(stash)),
        (Str("tokens", raw=True), List(raw)),
    ))
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
    fields = {key.text: value for key,
    value in got.entries if isinstance(key, Str)}
    origin = fields["origin"]
    stash = fields["stash"]
    raw = fields["tokens"]
    if not isinstance(origin, List) or not isinstance(stash,
    List) or not isinstance(raw, List):
        raise ValueError("malformed tokens")
    held: dict[int, Stashed] = {}
    for item in stash.items:
        key, start, end, kind, depth = _pair(item)
        held[int(key.value)] = Stashed(kind.text, int(start.value),
        int(end.value), int(depth.value))
    lexed = Prelexed(_text(fields["code"]),
    tuple(int(n.value) for n in origin.items), held)
    packed = tuple(
        (kind.text, value.text, int(start.value), int(end.value))
        for kind, value, start, end in (_pair(item) for item in raw.items)
    )
    return Tokens(_text(fields["source"]), lexed, packed)


def cli(stage: object) -> int:
    """Read stdin, run one stage, write stdout. A Pass or its name both
    work."""
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
    from fpl.lex import lex as lex_pass
    from fpl.parse import parse as parse_pass
    from fpl.desugar import desugar
    from fpl.elaborate import elaborate
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
'''


def obsidian() -> None:
    dot = ROOT / ".obsidian"
    dot.mkdir(exist_ok=True)
    (dot / "app.json").write_text(
        '{   "useMarkdownLinks": true,   "newLinkFormat": "relative",'
        '"alwaysUpdateLinks": true }'
    )
    (dot / "core-plugins.json").write_text(
        """{
  "file-explorer": true,
  "global-search": true,
  "switcher": true,
  "graph": true,
  "backlink": true,
  "outgoing-link": true,
  "tag-pane": true,
  "properties": true,
  "page-preview": true,
  "outline": true,
  "command-palette": true
}
"""
    )


def site() -> None:
    site_dir = ROOT / "site"
    (site_dir / "src" / "pages").mkdir(parents=True, exist_ok=True)
    (site_dir / "package.json").write_text(
        """{
  "name": "fpl-lit",
  "private": true,
  "type": "module",
  "scripts": { "build": "astro build" },
  "dependencies": { "astro": "^5.14.1" }
}
"""
    )
    (site_dir / "astro.config.mjs").write_text(
        """import { defineConfig } from "astro/config";

export default defineConfig({});
"""
    )
    (site_dir / "src" / "content.config.ts").write_text(
        """import { defineCollection } from "astro:content";
import { glob } from "astro/loaders";
import { z } from "astro/zod";

const concepts = defineCollection({
  loader: glob({
    pattern: "{01.01-boundary,01.02-pass,01.03-repr,01.04-compose,01.05-labs,01.06-nagini}/!(index).md",
    base: "..",
  }),
  schema: z.object({
    type: z.string(),
    title: z.string(),
    description: z.string(),
    tags: z.array(z.string()).optional(),
    engine: z.string().optional(),
  }),
});

export const collections = { concepts };
"""
    )
    (site_dir / "src" / "pages" / "index.astro").write_text(
        """---
import { getCollection } from "astro:content";
const concepts = (await getCollection("concepts")).sort((a,
b) => a.id.localeCompare(b.id));
---
<html lang="en">
  <body>
    <h1>FPL bootstrap</h1>
    <ul>
      {concepts.map((entry) => (
        <li><a href={`/${entry.id}`}>{entry.data.title}</a></li>
      ))}
    </ul>
  </body>
</html>
"""
    )
    (site_dir / "src" / "pages" / "[...slug].astro").write_text(
        """---
import { getCollection, render } from "astro:content";
export async function getStaticPaths() {
  const concepts = await getCollection("concepts");
  return concepts.map((entry) => ({ params: { slug: entry.id },
  props: { entry } }));
}
const { entry } = Astro.props;
const { Content } = await render(entry);
---
<html lang="en">
  <body>
    <p>{entry.data.type}</p>
    <h1>{entry.data.title}</h1>
    <Content />
  </body>
</html>
"""
    )
    (ROOT.parent / "_quarto.yml").write_text(
        """profile:
  default: site
  group:
    - [site, book]
execute:
  enabled: false
number-sections: false
filters:
  - .harness/scripts/essay.lua
"""
    )

    (ROOT.parent / "_quarto-site.yml").write_text(
        """project:
  type: website
  output-dir: .site
  render:
    - index.qmd
    - 01-bootstrap/README.md
    - 01-bootstrap/01.01-boundary/README.md
    - 01-bootstrap/01.02-pass/README.md
    - 01-bootstrap/01.03-repr/README.md
    - 01-bootstrap/01.04-compose/README.md
    - 01-bootstrap/01.05-labs/README.md
    - 01-bootstrap/01.06-nagini/README.md
    - 02-docs/README.md
    - 02-docs/02.04-notes/README.md
    - 03-fpl/README.md
    - 03-fpl/03.01-features/README.md
    - 01-bootstrap/01.01-boundary/01.01.01-source.qmd
    - 01-bootstrap/01.01-boundary/01.01.02-fon.qmd
    - 01-bootstrap/01.01-boundary/01.01.03-pipe.qmd
    - 01-bootstrap/01.01-boundary/01.01.04-render.qmd
    - 01-bootstrap/01.02-pass/01.02.01-lex.qmd
    - 01-bootstrap/01.02-pass/01.02.02-parse.qmd
    - 01-bootstrap/01.02-pass/01.02.03-resolve.qmd
    - 01-bootstrap/01.02-pass/01.02.04-expand.qmd
    - 01-bootstrap/01.02-pass/01.02.05-desugar.qmd
    - 01-bootstrap/01.02-pass/01.02.06-elaborate.qmd
    - 01-bootstrap/01.02-pass/01.02.07-lower.qmd
    - 01-bootstrap/01.02-pass/01.02.08-normalize.qmd
    - 01-bootstrap/01.02-pass/01.02.09-optimize.qmd
    - 01-bootstrap/01.02-pass/01.02.10-evaluate.qmd
    - 01-bootstrap/01.02-pass/01.02.11-codegen.qmd
    - 01-bootstrap/01.03-repr/01.03.01-source.qmd
    - 01-bootstrap/01.03-repr/01.03.02-tokens.qmd
    - 01-bootstrap/01.03-repr/01.03.03-syntax.qmd
    - 01-bootstrap/01.03-repr/01.03.04-resolved.qmd
    - 01-bootstrap/01.03-repr/01.03.05-expanded.qmd
    - 01-bootstrap/01.03-repr/01.03.06-elaborated.qmd
    - 01-bootstrap/01.03-repr/01.03.07-core.qmd
    - 01-bootstrap/01.04-compose/01.04.01-pass.qmd
    - 01-bootstrap/01.04-compose/01.04.02-run.qmd
    - 01-bootstrap/01.04-compose/01.04.03-inspect.qmd
    - 01-bootstrap/01.04-compose/01.04.04-build.qmd
    - 01-bootstrap/01.05-labs/01.05.01-pipeline.qmd
    - 01-bootstrap/01.06-nagini/01.06.01-advance.qmd
    - 02-docs/02.01-design.md
    - 02-docs/02.02-spec.md
    - 02-docs/02.03-roadmap.md
    - 02-docs/02.04-notes/02.04.01-issue-task-patch.md
    - 02-docs/02.04-notes/02.04.02-sober.md
    - 02-docs/02.04-notes/02.04.03-mediating-project.md
    - 03-fpl/03.01-features/draft1/spec.md
    - 03-fpl/03.01-features/draft2/spec.md
    - 03-fpl/03.01-features/draft3/spec.md
    - 03-fpl/03.01-features/match/spec.md
    - 03-fpl/03.01-features/server/spec.md
    - 03-fpl/03.01-features/sketch/spec.md
website:
  title: "FPL"
  site-url: https://psjg.github.io/fpl-lit-scratch
  page-navigation: true
  sidebar:
    search: true
    contents:
      - section: 01-bootstrap/README.md
        contents:
          - section: 01-bootstrap/01.01-boundary/README.md
            contents:
              - text: "1.1.1 Source"
                href: 01-bootstrap/01.01-boundary/01.01.01-source.qmd
              - text: "1.1.2 FON"
                href: 01-bootstrap/01.01-boundary/01.01.02-fon.qmd
              - text: "1.1.3 Pipe"
                href: 01-bootstrap/01.01-boundary/01.01.03-pipe.qmd
              - text: "1.1.4 Render"
                href: 01-bootstrap/01.01-boundary/01.01.04-render.qmd
          - section: 01-bootstrap/01.02-pass/README.md
            contents:
              - text: "1.2.1 Lex"
                href: 01-bootstrap/01.02-pass/01.02.01-lex.qmd
              - text: "1.2.2 Parse"
                href: 01-bootstrap/01.02-pass/01.02.02-parse.qmd
              - text: "1.2.3 Resolve"
                href: 01-bootstrap/01.02-pass/01.02.03-resolve.qmd
              - text: "1.2.4 Expand"
                href: 01-bootstrap/01.02-pass/01.02.04-expand.qmd
              - text: "1.2.5 Desugar"
                href: 01-bootstrap/01.02-pass/01.02.05-desugar.qmd
              - text: "1.2.6 Elaborate"
                href: 01-bootstrap/01.02-pass/01.02.06-elaborate.qmd
              - text: "1.2.7 Lower"
                href: 01-bootstrap/01.02-pass/01.02.07-lower.qmd
              - text: "1.2.8 Normalize"
                href: 01-bootstrap/01.02-pass/01.02.08-normalize.qmd
              - text: "1.2.9 Optimize"
                href: 01-bootstrap/01.02-pass/01.02.09-optimize.qmd
              - text: "1.2.10 Evaluate"
                href: 01-bootstrap/01.02-pass/01.02.10-evaluate.qmd
              - text: "1.2.11 Codegen"
                href: 01-bootstrap/01.02-pass/01.02.11-codegen.qmd
          - section: 01-bootstrap/01.03-repr/README.md
            contents:
              - text: "1.3.1 Source"
                href: 01-bootstrap/01.03-repr/01.03.01-source.qmd
              - text: "1.3.2 Tokens"
                href: 01-bootstrap/01.03-repr/01.03.02-tokens.qmd
              - text: "1.3.3 Syntax"
                href: 01-bootstrap/01.03-repr/01.03.03-syntax.qmd
              - text: "1.3.4 Resolved"
                href: 01-bootstrap/01.03-repr/01.03.04-resolved.qmd
              - text: "1.3.5 Expanded"
                href: 01-bootstrap/01.03-repr/01.03.05-expanded.qmd
              - text: "1.3.6 Elaborated"
                href: 01-bootstrap/01.03-repr/01.03.06-elaborated.qmd
              - text: "1.3.7 Core"
                href: 01-bootstrap/01.03-repr/01.03.07-core.qmd
          - section: 01-bootstrap/01.04-compose/README.md
            contents:
              - text: "1.4.1 Pass"
                href: 01-bootstrap/01.04-compose/01.04.01-pass.qmd
              - text: "1.4.2 Run"
                href: 01-bootstrap/01.04-compose/01.04.02-run.qmd
              - text: "1.4.3 Inspect"
                href: 01-bootstrap/01.04-compose/01.04.03-inspect.qmd
              - text: "1.4.4 Build"
                href: 01-bootstrap/01.04-compose/01.04.04-build.qmd
          - section: 01-bootstrap/01.05-labs/README.md
            contents:
              - text: "1.5.1 Pipeline"
                href: 01-bootstrap/01.05-labs/01.05.01-pipeline.qmd
          - section: 01-bootstrap/01.06-nagini/README.md
            contents:
              - text: "1.6.1 Advance"
                href: 01-bootstrap/01.06-nagini/01.06.01-advance.qmd
      - section: 02-docs/README.md
        contents:
          - text: "2.1 Design"
            href: 02-docs/02.01-design.md
          - text: "2.2 Spec"
            href: 02-docs/02.02-spec.md
          - text: "2.3 Roadmap"
            href: 02-docs/02.03-roadmap.md
          - section: 02-docs/02.04-notes/README.md
            contents:
              - text: "2.4.1 Issue, task, patch"
                href: 02-docs/02.04-notes/02.04.01-issue-task-patch.md
              - text: "2.4.2 Plumbing, not prophecy"
                href: 02-docs/02.04-notes/02.04.02-sober.md
              - text: "2.4.3 The project that mediates the language"
                href: 02-docs/02.04-notes/02.04.03-mediating-project.md
      - section: 03-fpl/README.md
        contents:
          - section: 03-fpl/03.01-features/README.md
            contents:
              - 03-fpl/03.01-features/draft1/spec.md
              - 03-fpl/03.01-features/draft2/spec.md
              - 03-fpl/03.01-features/draft3/spec.md
              - 03-fpl/03.01-features/match/spec.md
              - 03-fpl/03.01-features/server/spec.md
              - 03-fpl/03.01-features/sketch/spec.md
format:
  html:
    theme: cosmo
    toc: true
    toc-depth: 2
    code-overflow: wrap
"""
    )

    (ROOT.parent / "_quarto-book.yml").write_text(
        """project:
  type: book
  output-dir: .book
book:
  title: "FPL"
  subtitle: "Read in the order of the three scopes"
  author: "FPL"
  chapters:
    - index.qmd
    - part: "1 Bootstrap"
      chapters:
        - 01-bootstrap/01.01-boundary/01.01.01-source.qmd
        - 01-bootstrap/01.01-boundary/01.01.02-fon.qmd
        - 01-bootstrap/01.01-boundary/01.01.03-pipe.qmd
        - 01-bootstrap/01.01-boundary/01.01.04-render.qmd
        - 01-bootstrap/01.02-pass/01.02.01-lex.qmd
        - 01-bootstrap/01.02-pass/01.02.02-parse.qmd
        - 01-bootstrap/01.02-pass/01.02.03-resolve.qmd
        - 01-bootstrap/01.02-pass/01.02.04-expand.qmd
        - 01-bootstrap/01.02-pass/01.02.05-desugar.qmd
        - 01-bootstrap/01.02-pass/01.02.06-elaborate.qmd
        - 01-bootstrap/01.02-pass/01.02.07-lower.qmd
        - 01-bootstrap/01.02-pass/01.02.08-normalize.qmd
        - 01-bootstrap/01.02-pass/01.02.09-optimize.qmd
        - 01-bootstrap/01.02-pass/01.02.10-evaluate.qmd
        - 01-bootstrap/01.02-pass/01.02.11-codegen.qmd
        - 01-bootstrap/01.03-repr/01.03.01-source.qmd
        - 01-bootstrap/01.03-repr/01.03.02-tokens.qmd
        - 01-bootstrap/01.03-repr/01.03.03-syntax.qmd
        - 01-bootstrap/01.03-repr/01.03.04-resolved.qmd
        - 01-bootstrap/01.03-repr/01.03.05-expanded.qmd
        - 01-bootstrap/01.03-repr/01.03.06-elaborated.qmd
        - 01-bootstrap/01.03-repr/01.03.07-core.qmd
        - 01-bootstrap/01.04-compose/01.04.01-pass.qmd
        - 01-bootstrap/01.04-compose/01.04.02-run.qmd
        - 01-bootstrap/01.04-compose/01.04.03-inspect.qmd
        - 01-bootstrap/01.04-compose/01.04.04-build.qmd
        - 01-bootstrap/01.05-labs/01.05.01-pipeline.qmd
        - 01-bootstrap/01.06-nagini/01.06.01-advance.qmd
    - part: "2 Docs"
      chapters:
        - 02-docs/02.01-design.md
        - 02-docs/02.02-spec.md
        - 02-docs/02.03-roadmap.md
        - 02-docs/02.04-notes/02.04.01-issue-task-patch.md
        - 02-docs/02.04-notes/02.04.02-sober.md
        - 02-docs/02.04-notes/02.04.03-mediating-project.md
    - part: "3.1 Features"
      chapters:
        - 03-fpl/03.01-features/draft1/spec.md
        - 03-fpl/03.01-features/draft2/spec.md
        - 03-fpl/03.01-features/draft3/spec.md
        - 03-fpl/03.01-features/match/spec.md
        - 03-fpl/03.01-features/server/spec.md
        - 03-fpl/03.01-features/sketch/spec.md
format:
  pdf:
    pdf-engine: lualatex
    toc: true
    include-in-header:
      text: |
        \\renewenvironment{Shaded}{}{}
"""
    )


def main() -> None:
    signature()
    indexes()
    filled()
    hand()
    obsidian()
    site()


if __name__ == "__main__":
    main()
