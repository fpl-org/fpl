---
description: Create a new implementation worktree under worktrees/<name>/
argument-hint: <name> [base-branch]
---

Create a fresh FPL implementation attempt. See `docs/WORKTREES.md`.

Given `$1` = name (required), `$2` = base branch (default `main`):

1. From the repo root: `git worktree add worktrees/$1 -b attempt/$1 $2`
2. `cd worktrees/$1 && ../../scripts/setup` — wires `.githooks/`, the stacked-commit git
   config, and reports whether `.git/agent-identity` is set.
3. If identity is unset, tell the maintainer to run
   `scripts/agent-identity set <machine-account-email>` (see `docs/COMMITS.md`); do not
   proceed to commits until it is.
4. Report the worktree path and branch. Stop — implementation starts with `/new-feature` or
   `/impl-feature` inside the new worktree.

Do not scaffold `fpl/` or `features/` here unless the maintainer asks.
