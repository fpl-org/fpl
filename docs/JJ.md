# JJ.md — optional: Jujutsu for humans, alongside git

[Jujutsu](https://jj-vcs.github.io/jj/) (`jj`) is a git-compatible VCS that suits stacked
commits: amending a commit rebases its descendants by itself, there is no staging area, and a
change keeps its identity while its commits are rewritten. It is in the dev shell
(`docs/DEVSHELL.md`). **It is optional, and it is for humans.** Agents use git and
`scripts/acommit`: `jj` runs no hooks and has no scripting to put the gates back, so an agent
on `jj` would work outside the harness. The git-native flow of `docs/WORKFLOW.md` stays
canonical; `jj` writes the same git history.

## Set it up

In the **root checkout**, next to the existing `.git`:

```
jj git init --colocate
```

`jj` and `git` then operate on the same repository, and `git` shows a detached `HEAD`; that
is how a colocated repo looks, not a fault. Prefer read-only `git` commands from then on:
mixing mutating `git` and `jj` commands is what the jj docs warn against.

It does not work inside the linked worktrees of `docs/WORKTREES.md`. `jj` 0.41 refuses with
"Cannot create a colocated jj repo inside a Git worktree". A `jj workspace add` working copy
is no substitute for one: it has no `.git`, so the scripts and hooks of the harness do not
run there. Implementation worktrees stay on git.

## What jj skips, and what catches it

Checked with `jj` 0.41: `jj commit`, `jj describe` and `jj bookmark create` run **no git
hook**, and `jj git push` does not run `pre-push`. So none of these act on a `jj` commit:

| Gate | Hook it lives in | Who judges a `jj` commit instead |
| --- | --- | --- |
| message format, provenance, `Stack:`, agent territory | `commit-msg` | `scripts/commit-lint`, and the `commit-lint` check on the pull request |
| atomicity | `atomic-check` | nobody; keep commits atomic by hand |
| harness/worktree boundary, no commit on `main` | `pre-commit` | review; the ruleset on `main` (`docs/WORKFLOW.md`, rule 6) |
| branch names | `reference-transaction`, `pre-push` | the `branch-lint` check on the pull request |

Before pushing, run the message gates yourself:

```
scripts/commit-lint -b <branch> github/main..<bookmark>
```

A human commit carries `Human-Only: true` (`docs/COMMITS.md`). `jj` can add it to every
commit you make in this repository:

```
jj config set --repo templates.commit_trailers "'\"Human-Only: true\"'"
```

On a stack branch the message also needs `Stack: <name>`; add that line yourself.

## Command map (against docs/WORKFLOW.md)

| Operation | git-native | jj |
| --- | --- | --- |
| start a stack off base | `git switch -c stack/x/tip main` | `jj new main` |
| commit current work | `scripts/acommit …` | `jj commit -m "<message>"` |
| new change on top | edit + `acommit` | `jj new` then edit |
| amend a lower change | `git rebase -i --update-refs` | `jj edit <rev>`, edit, `jj new`; or `jj squash --into <rev>` |
| restack on moved base | `scripts/restack` | `jj rebase -d main` (descendants follow) |
| name a reviewable boundary | `git branch stack/x/1` | `jj bookmark set stack/x/1 -r @-` |
| view the stack | `git log --oneline --decorate main..HEAD` | `jj log` |
| push branches | `git push` | `jj git push` |

Bookmarks are git branches, so they follow `docs/BRANCHES.md`.

## Why it is not mandated

- Every agent and contributor would have to learn `jj`; the git-native flow needs only `git`
  and one helper.
- It bypasses every local gate (above). The forge-side checks make that survivable for a
  careful human. They do not make it a good default.
