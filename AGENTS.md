# AGENTS.md

The entry point for any agent — Claude, Codex, Gemini, a human, whatever — working in this
repo. Read it fully before touching anything. Nothing here is specific to one vendor; the only
vendor-specific notes live in `CLAUDE.md` and cover Claude Code's `.claude/` tooling.

## What this repo is right now

A **shared agent harness**. There is no compiler yet. The harness records the decisions that
are already settled and the conventions every implementation attempt must follow, so a fresh
session can pick up work without re-deciding groundwork.

The language *vision* is deliberately unwritten. It gets drawn out in a dedicated interview
(`docs/DESIGN.md`, populated by the `design-fpl` process). Until `DESIGN.md` has real content,
do not invent language semantics.

Keep talk about the vision sober, and the harness small: `docs/notes/2026-09-19-sober.md`.

## Repository layout

```
/                     the harness and the implementation, in any checkout
  AGENTS.md           this file
  CLAUDE.md           Claude Code tooling notes only
  .agents/            settled decisions and conventions for agents (vendor-neutral)
  docs/               the language's own documents: DESIGN.md, SPEC.md, ROADMAP.md, notes/
  bootstrap/          the walker: the Python implementation, a project of its own (the
                      package fpl, its tests, pyproject.toml, Makefile, mutants.allow,
                      HOLES.md, handoff/)
  fpl/                FPL's own tree, the language written in itself; so far it holds
                      fpl/features/, the conformance suite: the maintainer's specs and examples
  Makefile            runs the noslop lanes (make check, ...) in bootstrap/, and the walker from
                      the root: make run FILE=<file.fpl>, make repl
  .claude/            Claude Code commands, subagents, skill, hooks
  scripts/            acommit, commit-lint, restack, setup, agent-identity, new-worktree,
                      branch-lint, forward-only, layer, pr, review, land, task,
                      rad-cob-dagtaak;
                      crap, props, escapes, mutants, gates (the noslop gate);
                      diagrams (make map: the map of the code, never committed)
  quality/            the noslop gate's lanes, tool configs and pinned tools (.agents/QUALITY.md)
  tools/<name>/       tooling beside the language, each a uv project of its own, judged by make tools (.agents/QUALITY.md)
  flake.nix, flake.lock   the dev shell: one pinned toolchain for everyone (.agents/DEVSHELL.md)
                      and lib.limits, the one place the line limits are written: nix run .#gen-config
                      writes .editorconfig, quality/ruff-limits.toml and .githooks/commit-limits from it
  .githooks/          pre-commit, prepare-commit-msg, commit-msg, commit-rules (the rules, shared),
                      commit-limits (generated: the line limits),
                      atomic-check, reference-transaction, pre-push
                      (all enabled by scripts/setup)
  worktrees/<name>/   one implementation attempt each; git-ignored; see .agents/WORKTREES.md
```

**Worktree model.** Each attempt at implementing FPL lives in its own linked worktree at
`worktrees/<name>/` on its own branch. Any checkout may hold any work: a harness change can be
made mid-attempt, in the worktree.

- A session edits inside its own checkout only — never sideways into another worktree.
- One commit changes harness paths or implementation paths, never both (`.agents/WORKTREES.md`
  lists the sides). `scripts/commit-lint` judges every commit by it (`scripts/boundary`), at
  push and in CI; a refusal (`BOUNDARY-MIXED`) prints the command that splits the commit.
- `.githooks/pre-commit` refuses a `git commit` with `main` checked out; the real gate is
  `.githooks/reference-transaction`, which lets `main` move only to where `github/main` already
  is, so local merges are refused too. Work on a stack branch (`.agents/WORKFLOW.md`).
- Details and `git worktree` recipes: `.agents/WORKTREES.md`.

## Settled decisions

Full rationale in `.agents/STACK.md`. In brief:

- **Stack:** Python 3.12+ + [Lark](https://lark-parser.readthedocs.io) + frozen `@dataclass`
  nodes + structural `match` → tree-walking interpreter. Chosen for broad agent fluency.
- **Layered frontend:** source → **surface AST** → `desugar` → **tiny stable core AST** →
  semantics. All syntactic sugar dies in `desugar`. New syntax is a grammar + desugar change;
  the evaluator is left alone.
- **Spans everywhere:** every surface AST node carries a source span from parse time. Error
  quality is a feature.
- **Verifier:** `pyright` runs strict with exhaustive-`match` checking over the frozen
  dataclasses. A pyright error is a build failure.
- **Grammar ambiguity is a bug:** the grammar loads with `ambiguity='explicit'` and a test
  asserts zero ambiguity over the corpus.
- **Backend, later:** core IR → C → `clang` before anything LLVM. tree-sitter comes later and
  only for editor tooling, never as the semantic frontend.

## The one gate

Each worktree defines a single non-interactive check:

```
make check   # ruff, pyright and mypy strict, 100% branch coverage, CRAP <= 8, a property test per
             # module, layering, dependencies, dead and duplicate code (.agents/QUALITY.md)
```

`make check` green ⇔ the work is done. There is no other definition of done. Do not report a
feature complete on a red or unrun `make check`. Before a PR leaves draft, `make ready` adds
the long search: more examples, CrossHair, and mutation testing.

To run the walker, from the root of any checkout: `make run FILE=path/to/p.fpl` runs a file
and `make repl` starts the REPL (`make repl ARGS='--session s.log'`). The package is
`bootstrap/fpl`, so a bare `python -m fpl` from the root finds no module; `make check` ends by
running one example through `make run` and diffing it with its `.expected`.

The gate's configuration is policy: it lives in the harness (`quality/`), a change to it
carries `[policy]` and no code, and `make check` refuses to run against an uncommitted one.
Do not loosen a check to get to green; say which check is wrong and why.

## The oracle rule

Conformance is driven by human-authored fixtures:

```
fpl/features/<name>/spec.md               surface syntax, desugaring, semantics
fpl/features/<name>/examples/*.fpl        programs exercising the feature
fpl/features/<name>/examples/*.expected   expected stdout, or `ERROR: <line>:<col> <message>`
```

**The maintainer writes `spec.md`, the `.fpl` examples, and the `.expected` files.** An
agent's job is to make `make check` green against them. If an agent writes both a feature and
its own oracle, the oracle proves nothing.

`fpl/features/*/spec.md`, `fpl/features/*/examples/*`, `docs/DESIGN.md`, and `docs/SPEC.md` are
protected two ways: `.githooks/commit-msg` rejects a commit touching them without the literal
`[spec]` marker in the message, and the Claude `guard-specs` hook blocks the edit unless the
session sets `FPL_SPEC_EDIT=1`. Other harnesses honour the `[spec]` rule by convention. If you think a spec
is wrong, say so and let the maintainer decide — don't route around it.

## Commits & workflow

- One-time per clone/worktree: **`scripts/setup`** (wires `.githooks/`, stacked-commit git
  config, checks the author identity).
- Commit with **`scripts/acommit`** — it builds the message to `.agents/COMMITS.md` and sets the
  machine-account author. `.githooks/commit-msg` validates every commit independently; a soft
  LLM `atomic-check` blocks commits that bundle unrelated changes.
- Work in **stacked commits** — small, ordered, individually reviewable; **`scripts/restack`**
  rebases the stack when the base moves. See `.agents/WORKFLOW.md`. Prefer `jj`? `.agents/JJ.md`.
- **An approved PR is frozen.** Rewrite freely until the maintainer approves; after that,
  fix forward in a new PR on top (`.agents/WORKFLOW.md` rule 10; `.githooks/pre-push` refuses).
- **Land through a GitHub PR, always** (rebase-merge, never a local merge into `main`). The
  `Stack:` trailer on every commit keeps the grouping in the repo once the refs are deleted.
- Authorship model (machine account + `claude[bot]` App): `.agents/COMMITS.md`.
- The task graph (`scripts/task`, Radicle COBs in the repository): `.agents/TASKS.md`. The store
  exists; no task has been written to it yet.

## Coding standards

Lean code, elaborate formatted doc comments, TDD, semantic commits at logical checkpoints,
performance treated as a feature. (Claude sessions: load the `software-style` and
`software-method` skills.)

## Picking up work

0. Enter the dev shell: `direnv allow` once, or `nix develop -c <command>` (`.agents/DEVSHELL.md`;
   a bare interactive `nix develop` is unreliable on macOS). It carries every tool below at a
   pinned version and wires the git hooks on first entry. Check: `command -v ruff` prints a
   `/nix/store/…` path. It has no forge client; `gh` is an opt-in layer, per checkout:
   `scripts/layer on github`, or `nix develop .#github -c gh …`.
1. Read this file, `.agents/STACK.md`, `.agents/CONVENTIONS.md`, `.agents/COMMITS.md`, `.agents/WORKFLOW.md`,
   `.agents/BRANCHES.md`.
2. Pick a worktree (`git worktree list`) or make one (`scripts/new-worktree <name>`; see
   `.agents/WORKTREES.md`).
3. In it, find a feature whose `make check` is red — or scaffold one and stop for the
   maintainer to fill the fixtures.
4. Implement to green.
5. Check for code-vs-spec drift before declaring done.
