---
name: fpl:task:load
description: Create the tasks a units file lists, with .agents/skills/fpl:task/scripts/task load. Use when a plan's units (.agents/tasks/redo.tsv or a new file of the same shape) must become tasks, and before that to dry-run it with -n.
---

    .agents/skills/fpl:task/scripts/task load -n <file>    # say what it would create, write nothing
    .agents/skills/fpl:task/scripts/task load <file>       # create and link

A units file has five tab-separated columns, `#` lines ignored: `label`, `partOf`,
`blockedBy` (labels, comma-separated), `name`, `brief`; the title becomes `<label> <name>`.
`.agents/tasks/redo.tsv` is the harness redo's; a tasks store is not part of a clone, so the
file is how a reviewer sees in a diff what was loaded.

Always dry-run first. The loader refuses, before the first write and naming the unit,
whatever could not be taken back afterwards (a task is signed and replicated): a label that
is not one word or ends in `:`, labels differing only in case, a reference to a label the
file lacks, a title over 200 or a brief over 10 000 characters, a label two tasks of the store
share, a link this identity may not write, more than 64 blockers, a new loop of blockers or
parents, and a title or brief that `leak-check --text` flags (always in block mode).

- **Exit 0**: created and linked; every task and link read back from the store.
- **Exit 2**: refused before writing; or a `rad` that failed, or a write the reducer did not
  apply, after the rows before it were written. The message names the row; a rerun adds only
  what is missing.

A rerun creates nothing: a label that already is a task's first word, in any case, is skipped.
