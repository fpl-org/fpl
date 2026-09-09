# ROADMAP.md — milestones

Direction only. Scope and ordering shift as `docs/DESIGN.md` fills in. Each milestone lands as
a stack of small commits (`docs/WORKFLOW.md`) inside a worktree and is "done" only when
`make check` is green (`docs/CONVENTIONS.md`).

| # | Milestone | Done when |
| --- | --- | --- |
| 0 | **Worktree skeleton** — `pyproject.toml`, `Makefile` (`make check` = ruff + pyright + pytest), `fpl/` module stubs, `features/_template/`, empty conformance runner | `make check` runs and passes with zero features |
| 1 | **Lexer + parser** — `grammar.lark`, `parse.py` → surface AST with spans; `test_ambiguity.py` green | `features/arithmetic/` parses; zero Earley ambiguity |
| 2 | **Tree-walking eval** — `ast_core.py`, `desugar.py`, `eval.py` for the arithmetic core; `python -m fpl file.fpl` runs | `features/arithmetic/` conformance passes end to end |
| 3 | **Errors** — `errors.py`: every failure is `ERROR: <line>:<col> <message>` with a caret underline; no traceback escapes | error-case `.expected` files pass |
| 4 | **Desugar layer proven** — a second feature (e.g. `let`, `if`) added as grammar + desugar only, core AST unchanged | new feature green without touching `eval.py` |
| 5 | **Types** — `types.py`: a real check over core AST; type-error `.expected` cases | typed conformance passes; pyright still strict-clean |
| 6 | **Core IR** — lower core AST → small IR; `eval` runs on IR | conformance unchanged through the IR |
| 7 | **Backend: IR → C → clang** — `fpl build file.fpl` emits C, `clang` compiles it; same outputs as the interpreter | conformance suite passes against the compiled binary |
| 8 | **Editor tooling** — a tree-sitter grammar for highlighting / structural editing (separate from `grammar.lark`, not the semantic frontend) | grammar parses the `examples/` corpus |

**Explicitly deferred:** an LLVM backend (revisit only after milestone 7 is stable and there's
a concrete reason), a language server, a package system, self-hosting.
