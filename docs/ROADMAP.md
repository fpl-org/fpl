# ROADMAP.md — milestones

Direction only. Scope and ordering shift as `docs/DESIGN.md` fills in. Each milestone lands as
a stack of small commits (`.agents/WORKFLOW.md`) inside a worktree and is "done" only when
`make check` is green (`.agents/CONVENTIONS.md`).

## Before milestone 0

The table below starts at a worktree skeleton, but three phases come first and none of them is
language work. They are listed so the roadmap does not read as though the lexer begins tomorrow.

1. **The version control harness.** `scripts/`, `.githooks/`, `.agents/WORKFLOW.md` and the task
   graph of `.agents/TASKS.md`. Largely built; the store exists and holds nothing yet.
2. **The noslop harness.** `quality/` and the gate of `.agents/QUALITY.md`: every check, and a
   bad example each one must refuse, built before there is code to judge, so the pressure is
   there from the first commit. Built with milestone 0's skeleton, which is its first subject.
3. **Prototyping**, which is where milestone 0 begins.

`docs/notes/2026-09-19-sober.md` applies to both harness phases: a harness change earns its
place by making a reviewed, landed change cheaper, and there are no language changes yet for
either of them to make cheaper. That is a thing to watch, not a rule against them.

| # | Milestone | Done when |
| --- | --- | --- |
| 0 | **Worktree skeleton** — `bootstrap/pyproject.toml`, `bootstrap/Makefile` (`include ../quality/noslop.mk`), `bootstrap/fpl/` module stubs, `features/_template/`, empty conformance runner | `make ready` runs and passes with zero features |
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
