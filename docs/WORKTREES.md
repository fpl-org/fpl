# WORKTREES.md — the `worktrees/<name>/` layout

## The model

- **Root** (`/`) holds the **shared harness**: this `docs/`, `.claude/`, `scripts/`,
  `.githooks/`, `AGENTS.md`, `CLAUDE.md`. Edited from a root checkout on `main`.
- **`worktrees/<name>/`** is a linked git worktree — one **implementation attempt** at FPL,
  on its own branch. It holds `fpl/`, `features/`, `pyproject.toml`, `Makefile` — none of
  which exist at the root.

One repo, one `.git` object store, many working trees. In a worktree, `.git` is a *file*
pointing back to `<root>/.git/worktrees/<name>/`.

## Why children, not siblings

The common convention puts worktrees *beside* the main repo (`../fpl-featureX/`). We nest them
under `worktrees/` instead — everything for the project stays under one directory. Git does not
care where the path is; the only cost is that a nested worktree would otherwise show as
untracked content in the parent. The fix, already in place:

```
# .gitignore
worktrees/
```

`git worktree list` still tracks them normally — they are real worktrees, not ignored files.

## Recipes

```
# create an attempt (worktree add + agent identity + scripts/setup in one step)
scripts/new-worktree b                       # worktrees/b on attempt/b, from main
scripts/new-worktree b some-ref              # …from another base; -n for a dry run

# the same by hand
git worktree add worktrees/b -b attempt/b main
cd worktrees/b && ../../scripts/setup        # wire hooks + config in the new worktree

# list / inspect
git worktree list

# remove when done (branch stays until you delete it)
git worktree remove worktrees/b

# move one (how worktrees/a got here)
git worktree move <old-path> worktrees/a

# prune stale admin files after a manual delete
git worktree prune
```

`scripts/new-worktree` is the vendor-neutral entry point; `.claude/commands/new-worktree.md`
is a thin wrapper over it.

## Shared vs per-tree

| Path | Where it lives | Edited by |
| --- | --- | --- |
| `docs/`, `.claude/`, `scripts/`, `.githooks/`, `AGENTS.md`, `CLAUDE.md` | root, `main` | root sessions |
| `fpl/`, `features/`, `pyproject.toml`, `Makefile`, `tests/` | each `worktrees/<name>/` | that worktree's sessions |
| `.git/agent-identity` | per worktree (untracked) | `scripts/agent-identity` |

A root session never edits inside a worktree; a worktree session never edits the harness. To
change the harness while mid-attempt, commit in the worktree, `cd` to root, edit there.

**[gate]** `.githooks/pre-commit` enforces this table on the staged paths: a root checkout
rejects the second row's paths, a linked worktree rejects the first row's. Paths in neither
row pass on both sides. `FPL_BOUNDARY=block` (default) · `warn` (print, don't block) · `off`.
Git runs it for `git commit` only, so restacking a worktree onto a moved `main` is unaffected.

## Current state

- `worktrees/a/` — the first worktree (relocated from `./fpl_a`), branch `fpl_a`. Empty of
  implementation so far.
