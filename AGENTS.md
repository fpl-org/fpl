# AGENTS.md

The entry point for any agent, Claude, Codex, Gemini or a human, working in this repo. One
screen: what the repo is, the rules every harness must trust, and the skills that hold every
procedure. A skill (`.agents/skills/<name>/SKILL.md`) says when and how to run one script; the
docs under `.agents/` keep the decisions and their rationale; this file points at both.

## What this repo is right now

A shared agent harness around one implementation attempt, the walker in `bootstrap/`
(Python, Lark, a tree-walking interpreter; the rationale and the layering in
`.agents/STACK.md`, the module tree in `.agents/CONVENTIONS.md`). The language's own tree is
`fpl/`, so far the conformance suite `fpl/features/`. The language *vision* is deliberately
unwritten (`docs/DESIGN.md`, drawn out by the `design-fpl` interview); keep talk about it sober
(`docs/notes/2026-09-19-sober.md`) and do not invent semantics. Each implementation attempt is
a linked worktree under `worktrees/<name>/` on its own branch; a session edits inside its own
checkout only (`.agents/WORKTREES.md`). `make check` green is the one definition of done
(`.agents/QUALITY.md`); `make run FILE=<f.fpl>` and `make repl` run the walker from the root.

## The oracle rule

The maintainer writes `fpl/features/<name>/spec.md`, the `examples/*.fpl` and their
`.expected`; an agent makes `make check` green against them. An agent that writes both a
feature and its oracle proves nothing. If a spec looks wrong, say so and let him decide.

## Rules every harness holds

These are authorization-shaped, so they live here and nowhere else (Codex trusts only this file).

- Never edit `fpl/features/*/spec.md`, `fpl/features/*/examples/*`, `docs/DESIGN.md` or
  `docs/SPEC.md`: a commit touching them needs the literal `[spec]` marker
  (`.githooks/commit-msg`), and the Claude `guard-specs` hook blocks the edit itself.
- Commit only with `scripts/acommit` (the author is the machine account, the trailers carry the
  model and session; `.agents/COMMITS.md`). `.githooks/commit-msg` refuses anything else.
- One commit changes harness paths or implementation paths, never both (`scripts/boundary`).
- Land only through a pull request, with `scripts/land`: a fast-forward of `main` to the approved
  head; never the merge button, never a local merge. An approved pull request is frozen.
- Never edit `.github/workflows/`, the rulesets or the brake: the owner's paths.
- A pull request reaches the maintainer presented: a fresh session rewrites the branch into a
  literate series (`.claude/agents/presenter.md`) with a review card (`.agents/REVIEW-CARD.md`).

## The skills

Names are `fpl:<module>[:<skill>[:<sub>]]`, flat directories of the same name under
`.agents/skills/`; `.claude/skills` is a symbolic link to it, so every harness reads one tree.
A routine loads its sub-skills by name. A row marked *planned* has no skill yet and its unit
(S2-S6 in `.agents/tasks/redo.tsv`); until then its procedure is in the doc named.

| skill | when | script |
|---|---|---|
| `fpl:commit` (`:acommit`, `:identity`, `:lint`, `:boundary`, `:branch`) | making a commit, checking a range or a branch name | `acommit`, `agent-identity`, `commit-lint`, `boundary`, `branch-lint`; planned (S3), `.agents/COMMITS.md` |
| `fpl:series` (`:stamp`, `:manifest`, `:range`, `:revert`, `:restack`, `:present-check`) | giving a series its identity, moving or undoing it | `series`, `restack`, `present-check`; planned (S3), `.agents/COMMITS.md` |
| `fpl:present` (`:silent`, `:stamp`, one sub-skill per state) | telling a finished branch again for the maintainer | `present`; planned (S0, S3b), `.claude/agents/presenter.md` |
| `fpl:pr` (`:open`, `:body`, `:ready`, `:reviewer`, `:whoami`, `:tree`) | opening a draft, its body, making it ready, the tree of open pull requests | `pr`, `whoami-check`, `stack-tree`; planned (S2), `.agents/WORKFLOW.md` |
| `fpl:land` (`:dry-run`, `:land`, `:by-hand`) | landing an approved head on `main` | `land`; planned (S2), `.agents/WORKFLOW.md` |
| `fpl:worktree` (`:setup`, `:new`, `:layer`, `:sweep`) | a new checkout, its hooks, the forge layer | `setup`, `new-worktree`, `layer`, `sweep` |
| `fpl:leak` | text or a range before it leaves the machine | `leak-check`; planned (S4), `.agents/WORKFLOW.md` |
| `fpl:quality` (`:crap`, `:props`, `:escapes`, `:mutants`, `:gates`, `:diagrams`, `:skills`) | the gate's lanes, their proofs, the map | `crap`, `props`, `escapes`, `mutants`, `gates`, `diagrams`, `skills-cover`; `fpl:quality:skills` exists, the rest planned (S5), `.agents/QUALITY.md` |
| `fpl:task` (`:load`, `:tree`, `:ready`) | the task graph in the repository | `task`; planned (S5), `.agents/TASKS.md` |
| `fpl:review` (`:page`, `:serve`, `:export`, `:import`) | the Radicle review page | `review`, `review-serve`, `export-review`, `import-review`; planned (S6), `.agents/WORKFLOW.md` |
| `fpl:run` | running the walker: REPL, one expression, a file | `make repl`, `make run`, `nix run`; planned (pull request 192) |

## Picking up work

Enter the dev shell (`.agents/DEVSHELL.md`), make or pick a worktree (`.agents/WORKTREES.md`),
find a feature whose `make check` is red, implement to green, check for code-vs-spec drift.
Decisions and their reasons: `.agents/STACK.md`, `BRANCHES.md`, `CONVENTIONS.md`, `QUALITY.md`,
`COMMITS.md`, `WORKFLOW.md`, `TASKS.md`, `JJ.md`. Claude Code's own tooling: `CLAUDE.md`.
