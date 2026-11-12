---
name: fpl:task:tree
description: Print every task under its lane, with what each open leaf waits on, with .agents/skills/fpl:task/scripts/task tree. Use when asked how the units relate, which lane is where, or to see the whole graph at once.
---

    .agents/skills/fpl:task/scripts/task tree

Every task is drawn under the task it is part of (`-p` at `new`, or `task part`); a lane is
a task with parts. An open leaf says `ready`, or `<-` followed by the labels of the tasks it
waits on, so one command shows both shapes, the tree and the blocking.

- **Exit 0**: the tree. Tasks that block each other are drawn like any others, with `<-`;
  a blocker loop is named by `fpl:task:ready`.
- **Exit 1**: the tree, then a `#` line naming the tasks whose parents loop back on each
  other, which no root reaches and so are not drawn, or the parents this clone has not
  received, each drawn as a root marked `?` with its parts under it.
- **Exit 2**: no `rad`, or a store this clone has not initialised.

To act on what it shows, `fpl:task`; to list only what can start now, `fpl:task:ready`.
