---
name: fpl:series:present-check
description: Prove that a presented series is the series that was worked, with scripts/present-check. Use after presenting a branch, before its push; nothing runs it for you until the owner installs the series.yml draft, which runs it with one ref on every pull request.
---

    scripts/present-check [-B <base>] [-b <branch>] [--skip-quick] [W] P
    scripts/present-check classify [-B <base>] OLD NEW
    scripts/present-check rules [-B <base>] P

W is the work tip, P the presented one. With both it proves, cheapest first, stopping at the
first red: the trees are equal; both fork from `<base>` (default `main`) at the same commit;
`scripts/commit-lint` over `<base>..P` for the branch (`-b`, else P's name); when the series
script is in P's tree, every commit carries a Series-Id and the range holds one; every commit
reads as finished work (the rules `fix-on-series` and `review-prose`); and each lemma is green
alone, `make quick` in a detached worktree plus the self-tests that cover the paths it touched
(`--skip-quick` leaves `make quick` out for a docs-only series). It ends with the lemma list
and `git range-diff W...P`. With one ref the tree, merge-base and range-diff steps are left
out: that is what CI will have (`harness/workflows/series.yml`, a draft until the owner
installs it). `classify OLD NEW` prints how a push changed a pull request, one
word: `unchanged`, `presentation`, `relocation` or `content`; `rules P` builds nothing.

- **Exit 0**: green; push P and take the manifest (`fpl:series:manifest`).
- **Exit 1**: a check is red, named with the commit and the remedy. Fix P, never W.
- **Exit 2**: usage or tooling: a ref that does not resolve, no worktree, a tool missing.

`FPL_PRESENT_QUICK` and `FPL_PRESENT_LINT` name the commands; `present-check-self-test`
stands in a fixture through them. The full presenter routine is `.claude/agents/presenter.md`
(pull request 200 makes it a skill).
