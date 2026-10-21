---
name: fpl:commit:lint
description: Judge commits that already exist with scripts/commit-lint, the commit-msg hook in lint mode plus the boundary checker. Use before a push, before presenting a series, and to judge a range someone else made.
---

    scripts/commit-lint -b "$(git branch --show-current)" github/main..HEAD
    scripts/commit-lint -b <branch> "github/<parent>..HEAD"      a branch on an unmerged parent

`-b` names the branch the commits are headed for: with it the `Stack:` trailer must match
and an agent commit must sit on an agent branch; without it those two gates are skipped,
which is right for a range of `main`. The range is what the push adds, never the parent's
commits, which carry another `Stack:`. Merges are skipped. Each commit is judged by this
checkout's hook and checker, never by the commit's own tree, so a range from before a rule
existed is judged all the same; `.githooks/pre-push` runs it over what a push adds, and the
`commit-lint` workflow over every commit of a pull request, from `main`'s tree.

- **Exit 0**: `0 of N commits failed`. Push, or go on presenting.
- **Exit 1**: `FAIL <subject>` for each refused commit, with the rule, the part that fails and
  the remedy, as the hook prints them; a `BOUNDARY-MIXED` line is the checker's (load
  `fpl:commit:boundary`). Amend or `git rebase -i`, then lint again.
- **Exit 2**: usage, an empty range, a range git cannot read, or no executable hook or checker.

Agent addresses: `FPL_AGENT_EMAILS` when set (CI sets it inline), else `.github/agent-emails`.
