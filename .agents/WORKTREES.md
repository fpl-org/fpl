# WORKTREES.md — the `worktrees/<name>/` layout

## The model

- **Any checkout may hold any work.** The root checkout and each linked worktree
  `worktrees/<name>/` carry the whole tree, on their own branch; a harness change can be made
  in a worktree, mid-attempt, and an implementation change in the root.
- **One commit stays on one side.** The tree has two sides, reviewed and landed apart, and a
  commit changes paths of one of them, never both (below).

One repo, one `.git` object store, many working trees. In a worktree, `.git` is a *file*
pointing back to `<root>/.git/worktrees/<name>/`.

## What a checkout holds

```
.agents/      the agent docs: this file, WORKFLOW, COMMITS, BRANCHES, QUALITY, ...
docs/         the language's own: DESIGN.md, SPEC.md, ROADMAP.md, notes/
bootstrap/    the walker, a project of its own: its package fpl, tests, pyproject.toml,
              Makefile, mutants.allow, HOLES.md, handoff/
fpl/           FPL's own tree: so far fpl/features/, the conformance suite, the maintainer's
quality/ scripts/ .githooks/ .claude/    the harness
Makefile      runs the noslop lanes in bootstrap/ (make check, make ready, ...)
```

Paths inside FPL source that start with `/fpl/` (`/fpl/ext/asm`, `/fpl/lib/cat`) are the
language's namespace, not directories of the repository.

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

`scripts/sweep` tables every worktree and unattached branch (merged, commits `main` lacks by
patch, dirty files, pull request, owner) with a proposal: keep, review or archive. A dry run is
the default; `SWEEP_OWNER_YES=1 scripts/sweep --apply`, run from the main checkout, tags what it
removes and saves dirty files under `harness/sweep-archive/` there.

## The two sides

| Side | Paths |
| --- | --- |
| harness | `docs/`, `.agents/`, `.claude/`, `scripts/`, `quality/`, `.githooks/`, `AGENTS.md`, `CLAUDE.md`, `flake.nix`, `flake.lock`, `.envrc` |
| implementation | `bootstrap/`, `fpl/` (with `fpl/features/`), `tests/`, `pyproject.toml`, `Makefile`, `mutants.allow` |
| neutral | every other path (`README.md`, `.gitignore`, `.github/`, `tools/`, `LICENSE`, ...): goes with either side |

`fpl/` stays implementation after the move to `bootstrap/`: it becomes FPL's own tree.
A session edits inside its own checkout only, never inside another worktree; `.git/agent-identity`
is per worktree (untracked), set by `scripts/agent-identity`.

A change that needs both sides is two commits, harness first or implementation first, as the
stack wants. A commit is compared with its parent (a root commit with the empty tree), with
rename detection, and both paths of a rename count: `fpl/x` to `bootstrap/fpl/x` stays on one
side, `docs/x` to `bootstrap/x` is mixed.

**[gate]** The checker of `fpl:commit:boundary` judges one non-merge commit, and
`scripts/commit-lint` runs it on every commit of its range, with the checker of the checkout
that runs it, so a range from before the checker existed is judged too. commit-lint runs in
`pre-push` and in CI (the `commit-lint` workflow), so the rule binds every commit however it
was made: `git commit`, cherry-pick, rebase, amend, `--no-verify`, an unwired clone, `jj`.
Nothing judges it at commit time, and no variable switches it off. Paths are judged as bytes
(the C locale), so a name that is not UTF-8 is judged like any other.

Merges are not judged: commit-lint skips them, and `main`'s ruleset requires a linear history,
so a merge commit cannot land. A squash merge can, and it is the one landing this gate does not
see: it folds a pull request's one-sided commits into one commit on `main`, which may be mixed.
Land by rebase (`scripts/land` does). On 2026-10-06 one ruleset on `main` allowed only rebase
merges, a second allowed merge, squash and rebase, and the repository allowed squash. GitHub
applies the most restrictive version of a rule when rulesets overlap, which leaves rebase only;
that reading is GitHub's documentation, not a measured refusal.

A mixed commit is refused as `BOUNDARY-MIXED`, with the command that splits it in two, one
commit a side, with the old author, committer and message, the later commits of the branch
rebuilt on top and the branch alone moved. What the split does, what it refuses as
`BOUNDARY-TOOL` (a history it cannot rebuild faithfully, or a git command that failed: a gate
that cannot look does not pass), and the self-test that proves it under bash 5 and 3.2:
`fpl:commit:boundary`. Pushing a split of a published commit rewrites a published branch,
which wants coordination and never happens to an approved pull request (`.agents/WORKFLOW.md`,
rule 5).

## Current state

- `worktrees/a/` — the first worktree (relocated from `./fpl_a`), branch `fpl_a`. Empty of
  implementation so far.
