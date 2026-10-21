---
name: fpl:review:import
description: Use to bring a GitHub pull request and its review into a Radicle patch, once. Runs scripts/import-review; `review --serve` calls it for every open pull request.
---

# fpl:review:import

## What

`scripts/import-review` makes one pull request one patch (found again by `GitHub-PR:
<owner>/<repo>#<n>` in its description). The head becomes a revision based on the merge base,
so a stack shows its own layer; a new head is a new revision. Every comment, reply and verdict
becomes a comment on that revision, at the same lines.

## Why

After the import the patch is the record and replicates with the repository; the forge thread
is where it happened to be typed. Importing twice changes nothing.

## How

    S=$(git rev-parse --show-toplevel)/.agents/skills/fpl:review:import/scripts/import-review
    "$S" <number>...      # those pull requests
    "$S" --open           # every open one
    "$S" --dump <number>  # print the forge's data as JSON and stop
    "$S" --bundle <file>  # import from such a dump
    "$S" --self-test      # throwaway Radicle home

Needs `rad`, the key in the agent and a `github.com` remote (the forge layer of the worktree skills). It pushes
to the `rad` remote. Comments are signed by whoever ran it; the first line says who wrote them.

Exit: 0 done or self-test ok; 1 failure or failed self-test; 2 usage.
