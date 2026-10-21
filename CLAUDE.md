# CLAUDE.md

Read [`AGENTS.md`](AGENTS.md) first: it is the guide for every agent, Claude included, and names
the skills. This file covers only the Claude Code tooling under `.claude/`.

- **Skills**: `.claude/skills` is a symbolic link to `.agents/skills`, the source of every skill.
- **Hooks** (`.claude/settings.json`): `PreToolUse(Edit|Write)` runs `.claude/hooks/guard-specs.sh`,
  which blocks an edit to a protected spec unless the session sets `FPL_SPEC_EDIT=1`; `Stop` runs
  `.claude/hooks/stop-check.sh`, a best-effort `make fix` and `make quick` in an implementation worktree.
- **Subagents** (`.claude/agents/`): `spec-guardian`, `feature-impl`, `presenter`.
- **Slash commands** (`.claude/commands/`): thin wrappers over `.agents/CONVENTIONS.md`.
- **As the GitHub App** (`@claude` on an issue or pull request): the hooks are wired and
  `FPL_SESSION_ID` is set; commit with `scripts/acommit -M "<your model name>" …`.
- **Branches**: `agent/claude/…` when you choose; the flat `claude/<slug>` of the App and the cloud
  is the vendor escape hatch (`.agents/BRANCHES.md`). Load the `software-style` skill before code.
