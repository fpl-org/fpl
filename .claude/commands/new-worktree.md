---
description: Create a new implementation worktree under worktrees/<name>/
argument-hint: <name> [base-branch]
---

Create a fresh FPL implementation attempt. See `docs/WORKTREES.md`.

Given `$1` = name (required), `$2` = base branch (default `main`):

1. Run `scripts/new-worktree -a claude $1 $2`. It adds `worktrees/$1` on branch
   `agent/claude/attempt/$1` (agent commits need an agent branch, `docs/BRANCHES.md`), carries
   the root's agent identity into it, and runs `scripts/setup` there (hooks, stacked-commit
   git config, identity report).
2. If the output says the identity is NOT SET (the root had none to inherit), tell the
   maintainer to run `scripts/agent-identity set <machine-account-email>` inside the new
   worktree (see `docs/COMMITS.md`); do not proceed to commits until it is.
3. Report the worktree path and branch. Stop — implementation starts with `/new-feature` or
   `/impl-feature` inside the new worktree.

Do not scaffold `fpl/` or `features/` here unless the maintainer asks.
