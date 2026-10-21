---
name: fpl:pr:ready
description: Take a pull request out of draft once the bots are quiet, with .agents/skills/fpl:pr/scripts/pr --ready. Use when the series is presented and the card is on; Ready is the maintainer's signal to read, and the one door to it.
---

    .agents/skills/fpl:pr/scripts/pr --ready <number>

It reads the head: while a check run or a commit status is pending, or a review is requested
and unanswered, it waits, polling every `FPL_PR_POLL` seconds (15) for up to `FPL_PR_WAIT`
(900), then marks the pull request ready. `.github/CODEOWNERS` then asks the maintainer
itself. A bot that has not started its check yet is not pending to the forge: run this a
minute after the push. Run `wip-count` first: a ready pull request counts toward the
cap (`.agents/WORKFLOW.md`, The cap).

- **Exit 0**: `pr: #<n> is ready, the bots are quiet at <sha>`; or it was ready already.
- **Exit 1**: not quiet after the wait, naming each pending check, status or request; the head
  moved while it was read (run it again); the pull request is closed; or the token may not
  read checks (it needs Checks and Commit statuses read, WORKFLOW.md, The agent's credential).
