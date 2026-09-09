# CONVENTIONS.md — how an implementation worktree is laid out

Canonical for every agent. The Claude `fpl-conventions` skill and the `.claude/commands/*`
wrappers just point here. None of this exists yet — it is the shape a worktree session
creates on the first real implementation pass.

## Source tree (`fpl/` inside a worktree)

```
fpl/
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
tests/
  conftest.py            discovers features/*/examples/*.fpl, runs the driver, diffs .expected
  test_conformance.py
  test_ambiguity.py      asserts the grammar parses the corpus with zero Earley ambiguity
  test_grammar_lalr.py   (optional) grammar also loads under lalr
```

`.expected` format:

- Normal case: exact stdout of `python -m fpl <file>`.
- Error case: a single line `ERROR: <line>:<col> <message>` — no Python traceback ever reaches
  the user.

**The oracle rule:** the maintainer writes `spec.md`, the `.fpl` files, and the `.expected`
files. The agent makes `make check` green against them. `spec.md`, `DESIGN.md`, `SPEC.md` are
edit-protected (`[spec]` marker required).

## The gate (`make check` inside a worktree)

Runs, in order, non-interactively:

1. `ruff check fpl tests`
2. `pyright` — strict, `reportMatchNotExhaustive=error`
3. `pytest -q` — unit tests, `test_ambiguity`, conformance

Green ⇔ done. A feature with a red or unrun `make check` is not done.

## Adding a feature — the loop

1. `features/<name>/` scaffolded from `_template/` (`/new-feature` does this, then stops).
2. Maintainer fills `spec.md` + `examples/*.fpl` + `*.expected`.
3. Agent: `make check` is now red. Implement across `grammar.lark` → `desugar.py` →
   (rarely) `ast_core.py`/`eval.py` until green. Never touch `spec.md`.
4. Check for code-vs-spec drift, commit, done.
