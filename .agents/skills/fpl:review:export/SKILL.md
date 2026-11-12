---
name: fpl:review:export
description: Use to put what was written in the Radicle review onto the GitHub pull request, once. Runs scripts/export-review; posts as the machine account.
---

# fpl:review:export

## What

`scripts/export-review` posts the comments written in a Radicle patch, and not imported from
the forge, onto the pull request: a line comment as a review comment on those lines (a line
outside the diff becomes a plain comment naming it), a reply in its thread, a verdict as a
comment. The forge's approval stays the maintainer's own act.

## Why

People who found the project on the forge read the pull request. Each comment keeps one home:
the first line names the writer and signing key, the last is an HTML comment with the Radicle
id, which is how a second run skips it and `fpl:review:import` leaves it out.

## How

    S=$(git rev-parse --show-toplevel)/.agents/skills/fpl:review:export/scripts/export-review
    "$S" -n --open     # print what would be posted, post nothing
    "$S" <number>...   # those pull requests
    "$S" --open        # every patch whose pull request the forge lists as open
    "$S" --self-test   # throwaway Radicle home, offline

Posting is outward: dry-run first; the machine account's token does it (`.agents/WORKFLOW.md`).
It does not pass the leak gate, so read the text first.

Exit: 0 done or self-test ok; 1 failure (rad missing, forge refused) or failed self-test;
2 usage.
