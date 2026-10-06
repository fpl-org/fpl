# WORKTREES.md — the `worktrees/<name>/` layout

## The model

- **Any checkout may hold any work.** The root checkout and each linked worktree
  `worktrees/<name>/` carry the whole tree, on their own branch; a harness change can be made
  in a worktree, mid-attempt, and an implementation change in the root.
- **One commit stays on one side.** The tree has two sides, reviewed and landed apart, and a
  commit changes paths of one of them, never both (below).

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
scripts/new-worktree -a claude b             # …on agent/claude/attempt/b, for an agent to work in
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

## The two sides

| Side | Paths |
| --- | --- |
| harness | `docs/`, `agents/`, `.claude/`, `scripts/`, `quality/`, `.githooks/`, `AGENTS.md`, `CLAUDE.md`, `flake.nix`, `flake.lock`, `.envrc` |
| implementation | `bootstrap/`, `features/`, `fpl/`, `tests/`, `pyproject.toml`, `Makefile`, `mutants.allow` |
| neutral | every other path (`README.md`, `.gitignore`, `.github/`, `tools/`, `LICENSE`, ...): goes with either side |

`fpl/` stays implementation after the move to `bootstrap/`: it becomes FPL's own tree.
A session edits inside its own checkout only, never inside another worktree; `.git/agent-identity`
is per worktree (untracked), set by `scripts/agent-identity`.

A change that needs both sides is two commits, harness first or implementation first, as the
stack wants. A commit is compared with its parent (a root commit with the empty tree), with
rename detection, and both paths of a rename count: `fpl/x` to `bootstrap/fpl/x` stays on one
side, `docs/x` to `bootstrap/x` is mixed.

**[gate]** `scripts/boundary <commit>` judges one non-merge commit. `scripts/commit-lint` runs
it on every commit of its range, with the checker of the checkout that runs it, so a range
from before the checker existed is judged too. commit-lint runs in `pre-push` and in CI (the
`commit-lint` workflow), so the rule binds every commit however it was made: `git commit`,
cherry-pick, rebase, amend, `--no-verify`, an unwired clone, `jj`. Nothing judges it at commit
time, and no variable switches it off. Paths are judged as bytes (the C locale), so a name
that is not UTF-8 is judged like any other.

Merges are not judged: commit-lint skips them, and `main`'s ruleset requires a linear history,
so a merge commit cannot land. A squash merge can, and it is the one landing this gate does not
see: it folds a pull request's one-sided commits into one commit on `main`, which may be mixed.
Land by rebase (`scripts/land` does). On 2026-10-06 one ruleset on `main` allowed only rebase
merges, a second allowed merge, squash and rebase, and the repository allowed squash. GitHub
applies the most restrictive version of a rule when rulesets overlap, which leaves rebase only;
that reading is GitHub's documentation, not a measured refusal.

A mixed commit is refused as `BOUNDARY-MIXED`, with a few paths of each side, the counts and
the command that splits it, for a commit `<c>` on `<branch>`:

```
scripts/boundary --split <c> <branch>
```

It makes a harness commit (the commit's tree with its parent's implementation paths, so the
neutral paths go with it), then an implementation commit (the commit's own tree), both with the
old author, committer and message (give each its own message before the push), and rebuilds
every later commit of `<branch>` on top with its own tree. Merges stay merges, and a merge that
changed something of its own (an evil merge) keeps that change. `<branch>`, and only it, then
moves by compare-and-swap, and the command prints the `git update-ref` that moves it back.
Nothing is checked out: the work tree and the index stay as they are, staged, unstaged and
ignored files included, it runs on an unclean tree, and with `rebase.updateRefs` on (which
`scripts/setup` sets) a branch stacked on `<c>` still holds `<c>` after; split it the same way, which makes the same two commits.
A neutral path that takes the place of an implementation path of the parent (a file `tests`
where the directory `tests/` was) goes with the implementation half. A signature is dropped,
as it no longer matches.

The split refuses, as `BOUNDARY-TOOL` with a remedy line, where it would rebuild another
history than the commits hold: a shallow repository (`git fetch --unshallow`), a grafts file
(`.git/info/grafts`), a symbolic `<branch>` (it moves the branch it points at; name that one),
and a history in which a rebuilt commit carries a `mergetag` header, which would name a commit
that is no longer a parent. Parents are read from each commit's own header. Notes stay on the
old commits: the split names them and copies none (`git notes copy` does). If a remote-tracking
ref holds the commit, the refusal and the split say so: the split still runs, but pushing the
result rewrites a published branch, which wants coordination and never happens to an approved
pull request (`docs/WORKFLOW.md`, rule 5).

If a git command fails inside the checker it refuses too (`BOUNDARY-TOOL`, with the command,
git's words and a remedy line): a gate that cannot look does not pass. It judges the commit's own
bytes, never a replacement object's (`GIT_NO_REPLACE_OBJECTS=1`, in commit-lint too), and
switches off a `nocasematch` the caller hands down. `scripts/boundary-self-test` proves
the cases under bash 5 and, on a Mac, `/bin/bash` 3.2; `make gates` runs it.

## Current state

- `worktrees/a/` — the first worktree (relocated from `./fpl_a`), branch `fpl_a`. Empty of
  implementation so far.
