# CLAUDE.md

**The authoritative guide for every agent — including Claude — is [`AGENTS.md`](AGENTS.md).**
Read it first. This file only covers Claude Code tooling that lives under `.claude/`.

## Claude-specific tooling

- **Slash commands** (`.claude/commands/`): `/design-fpl`, `/new-worktree`, `/new-feature`,
  `/impl-feature`, `/spec-check`. Each is a thin wrapper that follows the conventions in
  [`.agents/CONVENTIONS.md`](.agents/CONVENTIONS.md) — the commands don't define anything the doc
  doesn't.
- **Subagents** (`.claude/agents/`): `spec-guardian` (read-only code-vs-spec drift review),
  `feature-impl` (implements one feature to a green `make check`).
- **Skill** (`.claude/skills/fpl-conventions/`): loads `AGENTS.md` + `.agents/CONVENTIONS.md` +
  `.agents/COMMITS.md` + `.agents/WORKFLOW.md` for Claude. The docs are the source of truth; the
  skill is just a trigger.
- **Hooks** (`.claude/settings.json`):
  - `PreToolUse(Edit|Write)` → `.claude/hooks/guard-specs.sh`: blocks edits to
    `features/*/spec.md` / `features/*/examples/*` / `docs/DESIGN.md` / `docs/SPEC.md`
    unless the session sets `FPL_SPEC_EDIT=1`. Mirrors the `[spec]`-marker check in `.githooks/commit-msg`.
  - `Stop` → `.claude/hooks/stop-check.sh`: in an implementation worktree, best-effort
    `make fix` + `make quick`; no-op at the harness root.

The git-level tooling (`scripts/acommit`, `scripts/commit-lint`, `scripts/restack`,
`scripts/setup`,
`scripts/new-worktree`, `scripts/branch-lint`, `scripts/forward-only`, `scripts/layer`,
`scripts/pr`, `scripts/land`, `.githooks/*`) is not
Claude-specific — see `AGENTS.md` and
`.agents/COMMITS.md`.

## Running as the GitHub App

When `@claude` on an issue or pull request starts you in GitHub Actions, the git hooks are
wired and your author address is the App's. A plain `git commit` without the trailer block
is refused. Commit with `scripts/acommit -M "<your model name>" -t … -s … -m … -b …`;
`FPL_SESSION_ID` is already set, and `Stack:` is derived from the branch.

## Branch names

Claude sessions that can choose their branch work on `agent/claude/…` (`.agents/BRANCHES.md`);
the hooks reject agent commits anywhere else. `claude-code-action` and Claude cloud sessions
emit flat `claude/<slug>` names, which the grammar admits as the vendor escape hatch — do not
reconfigure them to fake a hierarchy under `claude/`.

## Coding standards

Load the `software-style` skill before writing code, `software-method` before planning a
larger chunk. These are Claude skills; the underlying standards (lean code, formatted doc
comments, TDD, semantic commits, performance as a feature) apply to any agent.
