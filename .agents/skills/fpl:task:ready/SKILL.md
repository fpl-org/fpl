---
name: fpl:task:ready
description: List the tasks that can be picked up now, with .agents/skills/fpl:task/scripts/task ready. Use at the start of a session or when a unit lands, to choose the next unit of work.
---

    .agents/skills/fpl:task/scripts/task ready

A task is ready when it is open and every task in its `blockedBy` is done or dropped; a
blocker this clone does not know counts as open. A lane is left out while it has an open
part, since its parts are what is picked up; once every part is closed, closing the lane is
the work left, and it is listed.

- **Exit 0**: one task per line, `<id> <state> <title>`.
- **Exit 1**: the list, then `# waiting on each other, nothing here can start: a -> b -> a`
  for each loop; the tasks in it are left out. `grep -v '^#'` keeps the list; write `|| true`
  where the loop does not matter to the caller.
- **Exit 2**: refused: no `rad` on `PATH`, or a clone without a store.

Pick one, `start` it and `assign` it to yourself: `fpl:task`.
