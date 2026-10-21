---
name: fpl:worktree
description: The routine for a checkout of this repository, from a fresh clone or worktree to a shell with the forge tools it needs. Use when you start work in a clone that has no hooks yet, when an attempt needs its own worktree under worktrees/<name>/, when a script says gh or rad is not on PATH, or when the worktrees and branches want an inventory.
---

One repository, one object store, many working trees: the root checkout and the linked
worktrees under `worktrees/<name>/`, each on its own branch, every one a whole tree. The
model, the two sides a commit may change, and what a checkout holds: `.agents/WORKTREES.md`.
Its procedures are the four sub-skills; load the one the moment asks for, in this order when
you start from nothing:

1. `fpl:worktree:setup`: wire the hooks and the stacked-commit config of a checkout
   (`scripts/setup`, idempotent). The dev shell runs it on first entry; a worktree the app or
   `git worktree add` made needs it once.
2. `fpl:worktree:new`: an implementation attempt in its own worktree, on an agent branch,
   with the identity and the hooks already in place.
3. `fpl:worktree:layer`: the forge tools (`gh`, `glab`, `rad`) are opt-in layers of the dev
   shell; turn one on for this checkout when a script asks for it.

When the table of worktrees is long, `fpl:worktree:sweep` says what each one holds and what
may go; nothing goes without the owner's yes.

A session edits inside its own checkout only, never inside another worktree, and commits
only on an agent branch (`.agents/BRANCHES.md`), with `acommit`.
