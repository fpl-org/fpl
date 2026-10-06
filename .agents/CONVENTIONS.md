# CONVENTIONS.md — how the walker, the implementation, is laid out

Canonical for every agent. The Claude `fpl-conventions` skill and the `.claude/commands/*`
wrappers just point here. The walker, the Python implementation, is a project of its own in
`bootstrap/`: its package is `fpl`, so `import fpl` and the module names below are what they
were; only the directory moved, and with it the paths of its files. `features/`, the
conformance suite, stays at the root, above the project, because it is the language's, not the
walker's.

## Source tree (`bootstrap/fpl/`)

```
bootstrap/fpl/
  grammar.lark      syntax spec; the file the maintainer edits. Declarative only.
  parse.py          grammar → Lark tree → surface AST. Dumb. No semantics here.
  ast_surface.py    frozen @dataclass nodes; every node carries a Span.
  desugar.py        surface AST → core AST. All sugar is erased here.
  ast_core.py       the tiny stable core: Lit, Var, Lam, App, Let, If, BinOp, …
  eval.py           match-based tree-walking interpreter over core AST only.
  types.py          type-check pass over core AST (starts as a stub).
  errors.py         FplError(span, message) → caret-underlined source rendering.
  driver.py         parse → desugar → (typecheck) → eval. Shared by CLI and tests.
  repl.py           interactive loop.
  __main__.py       `python -m fpl file.fpl` runs a file; `python -m fpl` starts the REPL.
```

Hard rules:

- **`parse.py` holds zero semantics.** Meaning lives in `desugar.py` and `eval.py`.
- **`ast_core.py` stays small.** Adding syntax = grammar + desugar + tests. If a change needs
  a new core node, that's a design decision — flag it.
- **Spans from parse time** on every surface node, threaded through desugar so errors point at
  real source.
- **Frozen dataclasses**, so `pyright` strict + `reportMatchNotExhaustive` actually bites.

## Features and conformance

```
features/
  _template/
    spec.md
    examples/hello.fpl
    examples/hello.expected
  <name>/
    spec.md              maintainer-authored: surface syntax, desugaring, semantics
    examples/*.fpl        maintainer-authored programs
    examples/*.expected   maintainer-authored expected output
bootstrap/tests/
  corpus.py              finds features/ above the project: the examples every test reads
  test_conformance.py    runs the driver on features/*/examples/*.fpl, diffs .expected
  test_ambiguity.py      asserts the grammar parses the corpus with zero Earley ambiguity
```

`.expected` format:

- Normal case: exact stdout of `python -m fpl <file>`.
- Error case: a single line `ERROR: <line>:<col> <message>` — no Python traceback ever reaches
  the user.

**The oracle rule:** the maintainer writes `spec.md`, the `.fpl` files, and the `.expected`
files. The agent makes `make check` green against them. `spec.md`, the examples, `DESIGN.md`
and `SPEC.md` are edit-protected (`[spec]` marker required).

## The gate (`make check` at the root)

`bootstrap/Makefile` is `include ../quality/noslop.mk`, and the root's `Makefile` runs each
lane in `bootstrap/`, so `make check` from the root is the walker's gate. It runs ruff, strict pyright
(`reportMatchNotExhaustive=error`) and strict mypy, the tests (unit, `test_ambiguity`, conformance) under
100% branch coverage, and the structural checks of `.agents/QUALITY.md`: CRAP, a property test
per module, the layering of the source tree above, declared dependencies, dead and duplicate
code, and named waivers.

Green ⇔ done. A feature with a red or unrun `make check` is not done.

## Adding a feature — the loop

1. `features/<name>/` scaffolded from `_template/` (`/new-feature` does this, then stops).
2. Maintainer fills `spec.md` + `examples/*.fpl` + `*.expected`.
3. Agent: `make check` is now red. Implement across `grammar.lark` → `desugar.py` →
   (rarely) `ast_core.py`/`eval.py` until green. Never touch `spec.md`.
4. Check for code-vs-spec drift, commit, done.
