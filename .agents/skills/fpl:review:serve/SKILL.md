---
name: fpl:review:serve
description: Use to review the open pull requests as Radicle patches in the browser, hunk by hunk, with comments signed by your key. Runs scripts/review-serve, or `review --serve` to import first.
---

# fpl:review:serve

## What

`scripts/review-serve` serves one page on 127.0.0.1 from the repository's Radicle patches:
the queue head first, every file whole, a mark per hunk (approve `→`, not this `←`, comment
`c`), the merged ones grey above. What you write goes into the patch under your key.

## Why

The review is a record in the repository, not a thread on a forge. The page lands nothing
and writes nothing to the forge: approve in GitHub, and the lander lands it fast-forward.

## How

    S=$(git rev-parse --show-toplevel)/.agents/skills/fpl:review:serve/scripts/review-serve
    "$S" --fresh [--port <n>] # stop a running page, import open PRs, serve
    "$S"                      # serve what Radicle already holds, no import
    "$S" --self-test          # throwaway Radicle home

Needs `rad` and a repository that went through `rad init`. `--fresh` imports through
`fpl:review:import`, which needs a forge token: `FPL_FORGE_TOKEN`, the machine account's
credentials file (`.agents/WORKFLOW.md`), or else `gh auth token`; a failed import is
reported and the page serves what Radicle already holds. The address, token included, is
in `review-serve.pid` in the git directory (`git rev-parse --absolute-git-dir`, which a
linked worktree has of its own); a write needs the token. To send the written comments to
the forge, load `fpl:review:export`.

Exit: 0 clean stop or self-test ok; 1 a refusal (rad missing, no `rad init`) or a failed
self-test; 2 usage.
