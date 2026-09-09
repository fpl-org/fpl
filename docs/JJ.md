# JJ.md — optional: Jujutsu alongside git

[Jujutsu](https://jj-vcs.github.io/jj/) (`jj`) is a git-compatible VCS whose model fits the
stacked-commits workflow well: it auto-rebases descendants when you amend a commit, has no
staging area, and treats every change as a first-class, movable object. **It is optional.**
Nothing in the harness depends on it; the git-native flow in `docs/WORKFLOW.md` is canonical.
Use `jj` only if you (agent or human) prefer it — it writes the same git history and the same
commit convention.

## Set it up (colocated, non-destructive)

Inside a worktree, next to the existing `.git`:

```
jj git init --colocate
```

Both `jj` and `git` now operate on the same repo. `git` commands keep working; `jj` sees
git refs as bookmarks.

## Command map (against docs/WORKFLOW.md)

| Operation | git-native | jj |
| --- | --- | --- |
| start a stack off base | `git switch -c stack/x main` | `jj new main` |
| commit current work | `scripts/acommit …` | `jj commit -m "$(acommit-msg …)"` ¹ |
| new change on top | edit + `acommit` | `jj new` then edit |
| amend a lower change | `git rebase -i --update-refs` | `jj edit <rev>`, edit, `jj new` |
| restack on moved base | `scripts/restack` | `jj rebase -d main` (descendants follow automatically) |
| name a reviewable boundary | `git branch stack/x/1` | `jj bookmark set x/1 -r @-` |
| view the stack | `git log --oneline --decorate main..HEAD` | `jj log` |
| push branches | `git push` | `jj git push` |

¹ `jj` has no commit hooks, so it will **not** run `.githooks/commit-msg` or `atomic-check`.
If you commit via `jj`, run the message through the convention yourself and keep commits
atomic by hand. A thin `acommit-msg` (message-only, no `git commit`) can be added if `jj`
usage picks up — not built yet.

## Why it is not mandated

- Every agent and contributor would have to learn `jj`; the git-native flow needs only
  `git` + one helper.
- `jj` bypasses the git hooks that enforce `docs/COMMITS.md` and the oracle/atomicity gates.
- The rebase-heavy style rewrites SHAs freely, which fights GitHub PR review threads.

Revisit if the restack-by-hand cost in `docs/WORKFLOW.md` becomes a real drag.
