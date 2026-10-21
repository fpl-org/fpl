---
name: fpl:review:page
description: Use to read a branch's diff as one page with every changed file whole, before approving it. Runs scripts/review (the script of this skill); reads git refs only, no forge.
---

# fpl:review:page

## What

`scripts/review` renders `git diff` of a branch against `main` through `diff2html` as a page
and opens it. Every changed file is whole, not a hunk and three lines.

## Why

Whether a name is already bound, whether `set -e` bites here, is not in the hunk. A reviewer
who cannot see it approves what he cannot judge. It needs no forge, network or account.

## How

Run from the repository root, in the dev shell (`diff2html`):

    S=$(git rev-parse --show-toplevel)/.agents/skills/fpl:review:page/scripts/review
    "$S"                      # current branch against main
    "$S" -b <base> [<branch>] # against the branch below, in a stack
    "$S" -s                   # side by side
    "$S" -o <file>            # write the page there, do not open it

`FPL_REVIEW_NO_OPEN=1` leaves the browser closed on any run. `FPL_REVIEW_CONTEXT` sets the
lines of context (default 9999). `"$S" --serve` hands over to `fpl:review:serve`.

Exit: 0 the page path is printed; 1 detached HEAD, unknown branch or base, no commits over
the base, or `diff2html` missing.
