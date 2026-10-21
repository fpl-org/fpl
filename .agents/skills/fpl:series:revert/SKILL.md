---
name: fpl:series:revert
description: Undo a whole landed series in one commit on a new branch off main, with series revert. Use when a landed series must come out entire; the result goes through the usual pull request and a Series-Id of its own.
---

    .agents/skills/fpl:series/scripts/series revert <id> [<branch>]

Finds the series as `fpl:series:range` does, makes one commit on a new branch off `main`
(`SERIES_MAIN`) that reverts the contiguous range, commits it with `scripts/acommit` (type
`revert`, the trailer `Refs: series <id>`), and stamps it with a new Series-Id. The branch is
`agent/<lead>/stack/revert-<id>` when run from an agent branch `agent/<lead>/...`; elsewhere
it must be named. The commit is judged by the boundary checker first: a series that spans
harness and implementation paths cannot be undone in one commit.

- **Exit 0**: the branch exists, checked out, one commit above `main`; open its pull request.
- **Exit 1**: `usage`, `series-value` (not a Series-Id), `main-ref` and `range-*` (as
  `fpl:series:range`), `branch` (none can be derived: name one), `mint` (the branch name
  makes no Series-Id), `dirty` (a tree with changes), `revert-mixed` (both sides: undo the
  harness commits and the implementation commits apart, by hand), `revert-conflict` (a later
  change on main: revert by hand), `revert-empty` (main already lacks the series),
  `revert-refused` (acommit or a hook refused, printed as given), `revert-id` (the undo was
  committed but could not be stamped with its Series-Id; the message above says why).
  Nothing is left behind.

By hand, the same: `git switch -c agent/<id>/stack/revert-<id> github/main`,
`git revert -n <first>^..<last>`, then `scripts/acommit -t revert -s <scope> -m "<what the
series did>" -r "series <id>"` and `fpl:series:stamp`.
