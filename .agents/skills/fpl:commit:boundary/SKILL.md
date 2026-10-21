---
name: fpl:commit:boundary
description: Judge one commit for the harness/implementation boundary, or split a mixed commit in two, with the boundary checker in this skill's scripts/. Use when commit-lint, pre-push or CI refuses BOUNDARY-MIXED, and before committing a change that touches both sides.
---

    .agents/skills/fpl:commit:boundary/scripts/boundary <commit> [<branch>]      judge
    .agents/skills/fpl:commit:boundary/scripts/boundary --split <commit> <branch> split

One commit changes harness paths (`docs/`, `.agents/`, `.claude/`, `scripts/`, `quality/`,
`.githooks/`, `AGENTS.md`, `CLAUDE.md`, the flake, `.envrc`) or implementation paths
(`bootstrap/`, `fpl/`, `tests/`, `pyproject.toml`, `Makefile`, `mutants.allow`), never both;
every other path is neutral and goes with either. The two sides are reviewed and landed apart
(`.agents/WORKTREES.md`). The commit is compared with its parent, with rename detection, and
both ends of a rename count. `scripts/commit-lint` runs the checker on every commit of its
range, so the rule binds at push and in CI however the commit was made.

- **Exit 0**: judged, one side, and nothing is printed; or split, printing the two new
  commits, how many later commits were rebuilt, the notes left behind and the
  `git update-ref` that undoes the move.
- **Exit 1**, `BOUNDARY-MIXED`: a few paths of each side, the counts, and the `--split`
  command for the commit on its branch. Give the two halves their own messages before the push.
- **Exit 2**, `BOUNDARY-TOOL`: refused, never read as clean: wrong arguments, a git command
  that failed, a merge (judge the commits it brings), a shallow or grafted history, a
  symbolic branch, or a mergetag a rebuild would orphan. The message says what clears it.

`--split` builds a harness commit (the commit's tree with the parent's implementation paths,
so neutral paths go with it) and an implementation commit (the commit's tree), both with the
old author, committer and message. A neutral path that takes the place of an implementation
path of the parent (a file `tests` where the directory `tests/` was) goes with the
implementation half. It rebuilds every later commit of `<branch>` on top with its own tree
(merges stay merges), and moves `<branch>` alone by compare-and-swap, printing the
`git update-ref` that moves it back. Nothing is checked out; the work tree and index stay. A
signature is dropped; notes stay on the old commits; a remote-tracking ref that holds the
commit is named, since pushing the result rewrites a published branch. `boundary-self-test`
beside it proves every case under bash 5 and, on a Mac, `/bin/bash` 3.2.
