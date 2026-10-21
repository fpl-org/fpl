---
name: fpl:series:range
description: Find the commits of a landed series on main by its Series-Id, with series range. Use when a series must be read back, compared or reverted after it landed, when its branch and pull request are gone.
---

    .agents/skills/fpl:series/scripts/series range <id>

Prints the first-parent range `<base>..<tip>` on `main` (`SERIES_MAIN`) whose commits carry
`<id>`; the stack refs are deleted after landing and a linear landing leaves no merge, so the
trailer is the only in-repo record of which commits formed one unit. A series that landed
before the trailer existed carries only `Stack:`: `git log --grep='^Stack: <name>$'`.

- **Exit 0**: the range, one line.
- **Exit 1**: `usage` (no id), `series-value` (not a Series-Id), `main-ref` (`SERIES_MAIN`
  does not resolve), `range-none` (no commit on main carries the id), `range-root` (the series
  reaches main's root), `range-gap` (the commits are not one contiguous run: a commit of
  another series lies between them, and reverting that series leaves it there; revert the
  series' own commits by hand, `git revert -n` naming each, newest first).
