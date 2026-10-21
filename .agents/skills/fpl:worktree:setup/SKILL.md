---
name: fpl:worktree:setup
description: Make a clone or worktree ready for the commit workflow with scripts/setup, which wires the tracked hooks and the stacked-commit git config. Use once after git clone, once inside a worktree made by hand or by the app, and whenever a commit went through without the hooks or a rebase lost a stacked branch.
---

The hooks live in `.githooks/` and run only where `core.hooksPath` points at them; the
stacked-commit workflow relies on three settings (`.agents/WORKFLOW.md`). One script sets
all of it, from anywhere inside the checkout:

    scripts/setup

It is idempotent and writes nothing outside `git config --local`: `core.hooksPath` to
`.githooks`, `rebase.updateRefs` on (a rebase carries the branches stacked inside the range),
`rerere.enabled` and `rerere.autoUpdate` on (a conflict resolved once stays resolved), and
`commit.cleanup=scissors` (the rules the commit template carries never reach a commit). It
then lists the hooks git will run and says whether the agent author identity is set.

- **Exit 0**: done. The output names each hook that is wired; a hook that is there but not
  executable is named with the `chmod +x` that fixes it.
- `NOT SET` under "agent author identity": `acommit` will refuse until the machine
  account's address is set in this worktree (`agent-identity set <address>`, the
  noreply address of `.agents/COMMITS.md`). A human-only commit is unaffected.

The script stays in `scripts/` because the Claude GitHub App's workflow runs it by that path
on every runner. `fpl:worktree:new` runs it inside each worktree it makes; the dev shell runs
it on first entry and is silent after.
