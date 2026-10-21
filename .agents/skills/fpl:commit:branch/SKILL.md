---
name: fpl:commit:branch
description: Check a branch name against the grammar with scripts/branch-lint before the branch exists. Use when choosing a branch name, and when a hook refuses a push, a commit or a ref for its name.
---

    scripts/branch-lint <name>...        exit 0 when every name conforms, else 1 with a reason each
    scripts/branch-lint --parse <name>   print kind=, agent=, stack=, part=; exit 1 if it does not conform

The grammar, written once in the script's header and in prose in `.agents/BRANCHES.md`: an
agent's work is `agent/<id>/stack/<name>` (one pull request) or `agent/<id>/stack/<name>/tip`
with numbered boundary refs, `agent/<id>/attempt/<name>` for an implementation worktree; a
sub-series is `<parent>.<part>`, flat under the same prefix; `<id>` is `claude`, `codex`,
`copilot`, `cursor`, `jules` or `ai`. The flat vendor form `<id>/<slug>` is the escape hatch
for a tool that hard-codes its prefix, never a choice. `main` and `fpl_a` stand apart.

Every gate reads this one parser: the ref-name hooks, pre-push, `commit-msg` (which wants the
`Stack:` trailer the name implies, the one `scripts/acommit` writes), and CI's `branch-lint`
workflow. A name the parser refuses cannot carry an agent commit, so check it first.
