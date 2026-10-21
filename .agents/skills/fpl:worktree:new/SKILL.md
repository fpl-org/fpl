---
name: fpl:worktree:new
description: Create an implementation worktree under worktrees/<name>/ on its own branch, wired and with the agent identity, with the new-worktree script of this skill. Use when an attempt, a feature or a harness unit needs a checkout of its own; it does not scaffold code.
---

One command does the whole recipe, from any checkout of the repository:

    .agents/skills/fpl:worktree:new/scripts/new-worktree [-n] [-a <id>] <name> [base]

It adds `worktrees/<name>` from the root checkout, on the branch `attempt/<name>`, or
`agent/<id>/attempt/<name>` with `-a <id>` (`claude`, `codex`, ...): an agent's commits are
accepted on agent branches only (`.agents/BRANCHES.md`), so an attempt an agent will work in
needs `-a`. The base is `main` unless given. It then carries the root's agent identity into
the new worktree (the file is per worktree) and runs `scripts/setup` there
(`fpl:worktree:setup`). `-n` prints the commands and creates nothing.

- **Exit 0**: the last line is `ready: <path> on <branch>`. Work there; implementation starts
  with `/new-feature` or `/impl-feature` inside it.
- **Exit 2**: nothing was made. The message says why: a name outside
  `[a-z0-9][a-z0-9._-]*`, a branch `branch-lint` does not parse, a path or branch
  that already exists, a base that is not a commit, or no repository.
- `NOT SET` in the identity report: the root had no identity to inherit. Set it inside the
  new worktree (`agent-identity set <address>`) before any commit.

The script scaffolds nothing: `bootstrap/` and `fpl/features/` are the first implementation
session's job (`.agents/CONVENTIONS.md`), and only when the maintainer asks.
