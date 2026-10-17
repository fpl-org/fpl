"""Write the vault pages. Signature pages come from a table. Filled pages embed the seed."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
SEED = ROOT.parent / "fpl"

FRONT = """---
type: {type}
title: {title}
description: {description}
tags:
  - {tag}
engine: marimo
---

# {title}

{body}
"""


def page(path: Path, type_: str, title: str, description: str, body: str, tag: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        FRONT.format(type=type_, title=title, description=description, body=body, tag=tag)
    )


def cell(name: str, source: str) -> str:
    return f'```python {{.marimo name="{name}"}}\n{source.rstrip()}\n```\n'


def signature() -> None:
    """Pages with an arrow and no Python."""
    passes = [
        ("resolve", "Resolve", "Binders become identities.", "Syntax → Resolved", "parse", "expand"),
        ("expand", "Expand", "Sugar dies here. The term stays on the surface.", "Resolved → Expanded", "resolve", "elaborate"),
        ("lower", "Lower", "Reify the elaborated term into the dependent-CBPV core.", "Elaborated → Core", "elaborate", "normalize"),
        ("normalize", "Normalize", "A pass over the dependent-CBPV core.", "Core → Core", "lower", "optimize"),
        ("optimize", "Optimize", "A pass over the dependent-CBPV core.", "Core → Core", "normalize", "codegen"),
        ("codegen", "Codegen", "The core becomes the target.", "Core → Target", "optimize", "evaluate"),
    ]
    for name, title, description, arrow, prev, nxt in passes:
        body = (
            f"`{arrow}`\n\n"
            f"[{prev}]({prev}.md) is the previous arrow. [{nxt}]({nxt}.md) is the next.\n\n"
            "This page is the signature. The walker does not have this pass on its own yet.\n"
        )
        page(ROOT / "pass" / f"{name}.md", "Pass", title, description, body, "pass")
    reprs = [
        ("source", "Source", "The program text, after the ingress and before lex."),
        ("tokens", "Tokens", "What the lexer Lark yields. The parser Lark reads these and does not lex again."),
        ("syntax", "Syntax", "The surface ABT."),
        ("resolved", "Resolved", "Binders are identities."),
        ("expanded", "Expanded", "Sugar is gone. The term is still surface."),
        ("elaborated", "Elaborated", "Polarity, effects, and metavariables are known. Still surface-adjacent."),
        ("core", "Core", "The dependent-CBPV core. It later splits into Core.Value and Core.Comp. This trial keeps one sort."),
    ]
    for name, title, description in reprs:
        page(ROOT / "repr" / f"{name}.md", "Repr", title, description, description + "\n", "repr")
    page(
        ROOT / "compose" / "build.md",
        "Composition",
        "Build",
        "The release chain, a program that orders passes.",
        "```\nbuild = lex >> parse >> resolve >> expand >> elaborate >> lower >> optimize >> codegen\n```\n\n"
        "A `>>` chain orders passes. It is not the semantics.\n",
        "composition",
    )
    page(
        ROOT / "compose" / "inspect.md",
        "Composition",
        "Inspect",
        "Stop once elaboration has established what the core needs.",
        "```\ninspect = lex >> parse >> resolve >> expand >> elaborate\n```\n\n"
        "Elaboration establishes the semantic information. Lowering reifies it.\n",
        "composition",
    )


def indexes() -> None:
    def listing(folder: str, names: list[str]) -> str:
        return "\n".join(f"- [{name}]({name}.md)" for name in names) + "\n"

    for folder in ("pass", "repr", "compose", "boundary", "labs", "nagini"):
        (ROOT / folder).mkdir(exist_ok=True)
    (ROOT / "pass" / "index.md").write_text(
        "# Passes\n\n" + listing("pass", [
            "lex", "parse", "resolve", "expand", "desugar", "elaborate", "lower",
            "normalize", "optimize", "evaluate", "codegen",
        ])
    )
    (ROOT / "repr" / "index.md").write_text(
        "# Representations\n\n" + listing("repr", [
            "source", "tokens", "syntax", "resolved", "expanded", "elaborated", "core",
        ])
    )
    (ROOT / "compose" / "index.md").write_text(
        "# Compositions\n\n" + listing("compose", ["pass", "run", "build", "inspect"])
    )
    (ROOT / "boundary" / "index.md").write_text(
        "# Boundary\n\n" + listing("boundary", ["source", "fon", "pipe", "render"])
    )
    (ROOT / "index.md").write_text(
        "---\n"
        'okf_version: "0.2"\n'
        "---\n\n"
        "# FPL bootstrap\n\n"
        "The walker as a composition of passes. Inside one process the values are ABTs. "
        "FON is only the wire.\n\n"
        "## Passes\n\n"
        "- [lex](pass/lex.md)\n"
        "- [parse](pass/parse.md)\n"
        "- [desugar](pass/desugar.md)\n"
        "- [elaborate](pass/elaborate.md)\n"
        "- [evaluate](pass/evaluate.md)\n\n"
        "## Boundary\n\n"
        "- [source](boundary/source.md)\n"
        "- [pipe](boundary/pipe.md)\n"
        "- [render](boundary/render.md)\n"
    )
    (ROOT / "log.md").write_text(
        "# Log\n\n"
        "The literate trial of the bootstrap. The seed walker is unchanged.\n"
    )
    (ROOT / "labs" / "pipeline.md").write_text(
        "---\n"
        "type: Lab\n"
        "title: Pipeline\n"
        "description: The in-process chain beside the shell pipe.\n"
        "tags:\n"
        "  - lab\n"
        "engine: marimo\n"
        "---\n\n"
        "# Pipeline\n\n"
        "One cell is the in-process chain. The other is the same passes across FON.\n\n"
        + cell(
            "run",
            "import fpl\n\n"
            "run_now = fpl.lex >> fpl.parse >> fpl.desugar >> fpl.elaborate >> fpl.evaluate\n"
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
    """The lexer's output: the pre-lexed text and the tokens the second Lark will read."""

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
        (token.type, str(token), token.start_pos or 0, token.end_pos or 0) for token in got
    )


def _lex(source: str) -> Tokens:
    lexed = prelex(source)
    return Tokens(source, lexed, _pack(code_tokens(lexed.code)))


lex = Pass("lex", _lex)
'''

PARSE_TAIL = '''
from lark.lexer import Lexer

from fpl.arrow import Pass
from fpl.lex import Tokens, code_tokens


class _Replay(Lexer):
    """Yield tokens the lexer Lark already produced. This parser does not lex."""

    pending: list = []

    def __init__(self, lexer_conf: object) -> None:
        pass

    def lex(self, lexer_state: object, parser_state: object = None) -> object:
        yield from _Replay.pending


_REPLAY: Lark | None = None


def _replay_lark() -> Lark:
    global _REPLAY
    if _REPLAY is None:
        _REPLAY = Lark(
            GRAMMAR.read_text(),
            parser="lalr",
            lexer=_Replay,
            postlex=FplIndenter(),
            propagate_positions=True,
            maybe_placeholders=False,
        )
    return _REPLAY


def _from_tokens(raw: list) -> Tree[Token]:
    _Replay.pending = raw
    return _replay_lark().parse(" ")


def _as_tokens(raw: tuple[tuple[str, str, int, int], ...]) -> list[Token]:
    return [Token(kind, value, start_pos=start, end_pos=end) for kind, value, start, end in raw]


def _parse(tokens: Tokens) -> Program:
    """The parser Lark over the lexer Lark's tokens."""
    source, lexed = tokens.source, tokens.lexed
    try:
        tree = _from_tokens(_as_tokens(tokens.raw))
    except UnexpectedToken as failure:
        comment = isinstance(failure.token, Token) and failure.token.type in {"NOTE", "DOC"}
        message = "a comment cannot stand inside an enclosure" if comment else "unexpected input"
        raise FplError(placed(source, lexed, failure.pos_in_stream), message) from None
    except UnexpectedInput as failure:
        raise FplError(placed(source, lexed, failure.pos_in_stream), "unexpected input") from None
    except MisindentedError as failure:
        where_ = placed(source, lexed, failure.token.end_pos)
        raise FplError(where_, "dedent to a level never opened") from None
    lines = Lines(source)
    return _Build(source, lines, lexed).program(tree, lines.span(0))


parse = Pass("parse", _parse)
'''


def filled() -> None:
    lex_src = (SEED / "lex.py").read_text()
    page(
        ROOT / "pass" / "lex.md",
        "Pass",
        "Lex",
        "One Lark. Source in, tokens out. The hand counter stays inside this stage.",
        "The hand counter in the seed's `lex.py` counts pairs and tabs, because a grammar cannot. "
        "Then a Lark lexer, and nothing else, yields the tokens.\n\n"
        "[parse](parse.md) reads those tokens with a second Lark.\n\n"
        + cell("lex", wrap("lex", lex_src, LEX_TAIL)),
        "pass",
    )
    parse_src = (SEED / "parse.py").read_text()
    parse_src = parse_src.replace(
        'GRAMMAR = Path(__file__).with_name("grammar.lark")',
        'GRAMMAR = Path(__file__).resolve().parents[1] / "grammar.lark"',
    )
    parse_src = parse_src.replace(
        "return parser().parse(lexed.code)  # pyright: ignore[reportUnknownMemberType] -- lark types its text argument loosely",
        "return _from_tokens(code_tokens(lexed.code))",
    )
    page(
        ROOT / "pass" / "parse.md",
        "Pass",
        "Parse",
        "A second Lark. It reads the token stream and does not lex it again.",
        "Islands inside strings are new source, so those still go through the lexer Lark. "
        "The program itself is the token stream from [lex](lex.md).\n\n"
        + cell("parse", wrap("parse", parse_src, PARSE_TAIL)),
        "pass",
    )
    body = (SEED / "desugar.py").read_text()
    page(
        ROOT / "pass" / "desugar.md",
        "Pass",
        "Desugar",
        "The walker's fuse of resolve, expand, and lower. Not the type of expand.",
        "Today this is `Syntax → Core`. [resolve](resolve.md), [expand](expand.md), and "
        "[lower](lower.md) are the arrows it stands in for.\n\n"
        + cell(
            "desugar",
            wrap(
                "desugar",
                "from fpl.arrow import Pass\n\n" + body,
                '_desugar_fn = desugar\ndesugar = Pass("desugar", _desugar_fn)\n',
            ),
        ),
        "pass",
    )
    body = (SEED / "types.py").read_text()
    page(
        ROOT / "pass" / "elaborate.md",
        "Pass",
        "Elaborate",
        "Establish polarity, effects, and metavariables. The term stays surface-adjacent.",
        "[desugar](desugar.md) feeds this. [lower](lower.md) is what reifies the core, and the walker has not split that out yet.\n\n"
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
        ROOT / "pass" / "evaluate.md",
        "Pass",
        "Evaluate",
        "Core statements to the stacks each run line leaves. Fuel is the walker's bound.",
        "The environment rides inside the call. This wrapper closes over the walker's fuel.\n\n"
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
        ROOT / "boundary" / "fon.md",
        "Pass",
        "FON",
        "The inert codec. It reads and writes data. It does not elaborate.",
        "This is the seed's FON reader and writer.\n\n"
        + cell("fon", "from fpl.arrow import Pass\n\n" + body + '\nfon = Pass("fon", read)\n'),
        "boundary",
    )


def hand() -> None:
    page(
        ROOT / "compose" / "pass.md",
        "Composition",
        "Pass",
        "A pass is one object. >> composes two of them.",
        "Python has no pipe operator. `>>` on a Pass is composition. On an int it stays a shift.\n\n"
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
        ROOT / "compose" / "run.md",
        "Composition",
        "Run",
        "The walker's prefix, in-process.",
        "```\nrun = lex >> parse >> resolve >> expand >> elaborate >> lower >> evaluate\n```\n\n"
        "The executable chain is the prefix the walker actually runs. `desugar` stands in for "
        "resolve, expand, and lower.\n\n"
        + cell(
            "run",
            '''
from fpl.ast_core import Run
from fpl.desugar import desugar, listing
from fpl.elaborate import elaborate
from fpl.errors import FplError
from fpl.evaluate import evaluate
from fpl.lex import lex
from fpl.parse import parse
from fpl.print import render

run_now = lex >> parse >> desugar >> elaborate >> evaluate


def run_file(file: str) -> int:
    """Run one file the way the seed walker does. Goals go to stderr."""
    source = open(file, encoding="utf-8").read()
    try:
        text = render(listing(run_now(source)))
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
        ROOT / "boundary" / "pipe.md",
        "Pass",
        "Pipe",
        "defonify >> stage >> fonify, except at the two ends.",
        "`fonify` is the whole trip to the wire. `source` only fonifies. `render` only defonifies.\n\n"
        + cell("pipe", PIPE),
        "boundary",
    )
    page(
        ROOT / "boundary" / "source.md",
        "Pass",
        "Source",
        "Bytes in, FON out. Not a compiler pass.",
        "The pipe does not start on FON. This is the ingress.\n\n"
        + cell(
            "source",
            '''
import sys

from fpl.pipe import cli


def main() -> None:
    sys.exit(cli("source"))


if __name__ == "__main__":
    main()
'''.lstrip(),
        ),
        "boundary",
    )
    page(
        ROOT / "boundary" / "render.md",
        "Pass",
        "Render",
        "FON in, text out. Not a compiler pass.",
        "The pipe ends in text a person can read.\n\n"
        + cell(
            "render",
            '''
import sys

from fpl.pipe import cli


def main() -> None:
    sys.exit(cli("render"))


if __name__ == "__main__":
    main()
'''.lstrip(),
        ),
        "boundary",
    )
    (ROOT / "nagini").mkdir(exist_ok=True)
    (ROOT / "nagini" / "advance.md").write_text(
        "---\n"
        "type: Pass\n"
        "title: Advance\n"
        "description: One pure function on a frozen node, for Nagini.\n"
        "tags:\n"
        "  - pass\n"
        "---\n\n"
        "# Advance\n\n"
        "Nagini checks this. It does not call Lark, and it does not override a dunder.\n\n"
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
        raise FplError(__import__("fpl.errors", fromlist=["Span"]).Span(1, 1), "expected text")
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
        (Str("origin", raw=True), List(tuple(_num(n) for n in tokens.lexed.origin))),
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
    fields = {key.text: value for key, value in got.entries if isinstance(key, Str)}
    origin = fields["origin"]
    stash = fields["stash"]
    raw = fields["tokens"]
    if not isinstance(origin, List) or not isinstance(stash, List) or not isinstance(raw, List):
        raise ValueError("malformed tokens")
    held: dict[int, Stashed] = {}
    for item in stash.items:
        key, start, end, kind, depth = _pair(item)
        held[int(key.value)] = Stashed(kind.text, int(start.value), int(end.value), int(depth.value))
    lexed = Prelexed(_text(fields["code"]), tuple(int(n.value) for n in origin.items), held)
    packed = tuple(
        (kind.text, value.text, int(start.value), int(end.value))
        for kind, value, start, end in (_pair(item) for item in raw.items)
    )
    return Tokens(_text(fields["source"]), lexed, packed)


def cli(stage: object) -> int:
    """Read stdin, run one stage, write stdout. A Pass or its name both work."""
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
        '{\n  "useMarkdownLinks": true,\n  "newLinkFormat": "relative",\n  "alwaysUpdateLinks": true\n}\n'
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
    pattern: "{pass,repr,compose,boundary,labs}/!(index).md",
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
const concepts = (await getCollection("concepts")).sort((a, b) => a.id.localeCompare(b.id));
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
  return concepts.map((entry) => ({ params: { slug: entry.id }, props: { entry } }));
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
    (ROOT / "_quarto.yml").write_text(
        """project:
  type: website
  render:
    - "**/*.qmd"
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

