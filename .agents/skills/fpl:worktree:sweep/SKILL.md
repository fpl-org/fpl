---
name: fpl:worktree:sweep
description: Table every worktree and unattached branch (merged, commits main lacks by patch, dirty files, pull request, owner) with a proposal, keep, review or archive, with the sweep script of this skill. Use when the worktrees pile up or a branch's state is in question; only the owner applies the archive.
---

    .agents/skills/fpl:worktree:sweep/scripts/sweep [--dry-run]         the table, nothing changed
    SWEEP_OWNER_YES=1 .agents/skills/fpl:worktree:sweep/scripts/sweep --apply [name ...]
    .agents/skills/fpl:worktree:sweep/scripts/sweep --self-test

The dry run is the default and reads the repository without touching it; the forge is asked
once, read-only, with the machine account's token, for the pull request of each branch
(`pr` is `?` when it was not asked or did not answer in full). One row per linked worktree
and per branch no worktree holds: kind, name, branch, merged, new, dirty, pr, owner, action
and the reason in words. The first rule that fits decides the action: *keep* for the
do-not-touch list, the base branch, Cursor's and an app session's worktrees and an open pull
request; *review* for what a person must decide (locked, directory gone, PSJ's, touched in
the last hour, commits the base lacks); *archive* when everything it committed is in the
base. The rules in full are the header of the script.

`--apply` is the only way anything changes, needs `SWEEP_OWNER_YES=1` (the owner's yes) and
runs only in the main checkout. Per archive row, in the order that loses nothing: the dirty
and staged files as patches under `harness/sweep-archive/` (git-ignored, mode 600), a tag
`archive/<branch>` on the head, then the worktree and the branch go. A head that moved since
the table was made is skipped.

- **Exit 0**: the table, or the apply report, one line per row.
- **Exit 1**: refused, with the rule in brackets and the remedy: a run outside the main
  checkout, a forge that did not answer, an archive file that exists or would be written
  through a symlink. Nothing was changed.

An agent runs the dry run and reports; it never sets `SWEEP_OWNER_YES`.
