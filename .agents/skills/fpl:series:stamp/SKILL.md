---
name: fpl:series:stamp
description: Put one Series-Id on every commit of a range with series stamp, by a rebase that amends messages only. Use before a branch is pushed for review or presented, and after a revert; refused once the maintainer has spoken on the pull request.
---

    .agents/skills/fpl:series/scripts/series stamp <B>..HEAD [<id>]

The range must end at HEAD on a branch that is not `main` or detached, with `<B>` an ancestor
of HEAD. The id is the one the range already carries, else `<id>`, else a fresh mint. A
`git rebase --update-refs --exec` adds the trailer to each commit; every local branch pointing
into the range moves with it, and the author, the tree and every other trailer stay. Stamping
twice changes no hash. Run it before the `Presented-By:` stamp of the presenter routine
(pull request 200) and before any check or manifest: nothing touches a message after the
manifest is taken.

- **Exit 0**: stamped; the id is printed.
- **Exit 1**: refused before the rebase, the branch untouched: `range`, `branch` or `base`
  (fix the arguments), `dirty` (a staged or unstaged change: commit it or set it aside),
  `checked-out` (a branch in the range is checked out in another worktree: switch it off
  there), `series-mixed` (two ids in the range: fix the stray commit),
  `owner-spoke` (the maintainer has reviewed, approved or commented on the pull request of
  this branch or of a branch the rebase would move: a rewrite after that is a question to
  him, not a tool's call; present the history as built), `forge-token` (no machine-account
  token: `gh auth login` as it), `forge-query` (the forge did not answer: a refusal, never a
  pass), `tool` (no scratch file for the script in the git directory: make it writable).
  `rebase`: the rebase was refused by a hook and undone; fix what the message names and stamp
  again.

The forge is only read, as the machine account, pinned to `fpl-org/fpl` (`SERIES_REPO`) and
`psjg` (`SERIES_OWNER`).
