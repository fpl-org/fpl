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

## Repository layout

```
/                     shared harness — edited from a root checkout
  AGENTS.md           this file
  CLAUDE.md           Claude Code tooling notes only
  docs/               settled decisions and conventions (vendor-neutral)
  .claude/            Claude Code commands, subagents, skill, hooks
  scripts/            acommit, commit-lint, restack, setup, agent-identity, new-worktree,
                      branch-lint, layer, pr, land
  flake.nix, flake.lock   the dev shell: one pinned toolchain for everyone (docs/DEVSHELL.md)
  .githooks/          pre-commit, commit-msg, atomic-check, reference-transaction, pre-push
                      (all enabled by scripts/setup)
  worktrees/<name>/   one implementation attempt each; git-ignored; see docs/WORKTREES.md
```

**Worktree model.** The root holds the harness. Each attempt at implementing FPL lives in its
own linked worktree at `worktrees/<name>/` on its own branch.

- A root session edits the harness only — never files inside a `worktrees/<name>/`.
- A worktree session edits that worktree only — never up into the harness or sideways into
  another worktree.
- `.githooks/pre-commit` gates both rules on the staged paths (`FPL_BOUNDARY=warn` overrides).
  It also refuses a `git commit` with `main` checked out; the real gate is
  `.githooks/reference-transaction`, which lets `main` move only to where `origin/main` already
  is, so local merges are refused too. Work on a stack branch (`docs/WORKFLOW.md`).
- Details and `git worktree` recipes: `docs/WORKTREES.md`.

## Settled decisions

Full rationale in `docs/STACK.md`. In brief:

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
make check   # lint + pyright (strict) + pytest (unit + grammar-ambiguity + conformance)
```

`make check` green ⇔ the work is done. There is no other definition of done. Do not report a
feature complete on a red or unrun `make check`.

## The oracle rule

Conformance is driven by human-authored fixtures:

```
features/<name>/spec.md               surface syntax, desugaring, semantics
features/<name>/examples/*.fpl        programs exercising the feature
features/<name>/examples/*.expected   expected stdout, or `ERROR: <line>:<col> <message>`
```

**The maintainer writes `spec.md`, the `.fpl` examples, and the `.expected` files.** An
agent's job is to make `make check` green against them. If an agent writes both a feature and
its own oracle, the oracle proves nothing.

`features/*/spec.md`, `docs/DESIGN.md`, and `docs/SPEC.md` are protected two ways:
`.githooks/commit-msg` rejects a commit touching them without the literal `[spec]` marker in
the message, and the Claude `guard-specs` hook blocks the edit unless the session sets
`FPL_SPEC_EDIT=1`. Other harnesses honour the `[spec]` rule by convention. If you think a spec
is wrong, say so and let the maintainer decide — don't route around it.

## Commits & workflow

- One-time per clone/worktree: **`scripts/setup`** (wires `.githooks/`, stacked-commit git
  config, checks the author identity).
- Commit with **`scripts/acommit`** — it builds the message to `docs/COMMITS.md` and sets the
  machine-account author. `.githooks/commit-msg` validates every commit independently; a soft
  LLM `atomic-check` blocks commits that bundle unrelated changes.
- Work in **stacked commits** — small, ordered, individually reviewable; **`scripts/restack`**
  rebases the stack when the base moves. See `docs/WORKFLOW.md`. Prefer `jj`? `docs/JJ.md`.
- **Land through a GitHub PR, always** (rebase-merge, never a local merge into `main`). The
  `Stack:` trailer on every commit keeps the grouping in the repo once the refs are deleted.
- Authorship model (machine account + `claude[bot]` App): `docs/COMMITS.md`.

## Coding standards

Lean code, elaborate formatted doc comments, TDD, semantic commits at logical checkpoints,
performance treated as a feature. (Claude sessions: load the `software-style` and
`software-method` skills.)

## Picking up work

0. Enter the dev shell: `direnv allow` once, or `nix develop -c <command>` (`docs/DEVSHELL.md`;
   a bare interactive `nix develop` is unreliable on macOS). It carries every tool below at a
   pinned version and wires the git hooks on first entry. Check: `command -v ruff` prints a
   `/nix/store/…` path. It has no forge client; `gh` is an opt-in layer, per checkout:
   `scripts/layer on github`, or `nix develop .#github -c gh …`.
1. Read this file, `docs/STACK.md`, `docs/CONVENTIONS.md`, `docs/COMMITS.md`, `docs/WORKFLOW.md`,
   `docs/BRANCHES.md`.
2. Pick a worktree (`git worktree list`) or make one (`scripts/new-worktree <name>`; see
   `docs/WORKTREES.md`).
3. In it, find a feature whose `make check` is red — or scaffold one and stop for the
   maintainer to fill the fixtures.
4. Implement to green.
5. Check for code-vs-spec drift before declaring done.
