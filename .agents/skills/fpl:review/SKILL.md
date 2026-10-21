---
name: fpl:review
description: Use when a branch or pull request is to be read before approval, or review must move between GitHub and Radicle. Routine over fpl:review:page, :serve, :import and :export.
---

# fpl:review

## What

The routine that reads a change with the whole file around it and keeps the conversation in
the repository. Radicle is the mirror of record for reviews; the forge is where people type.

## Why

A forge hunk hides what judges it. A review that lives only on the forge is lost with it.

## How

1. One branch or diff: load `fpl:review:page`. Done.
2. Patches in the browser: load `fpl:review:serve`; `--fresh` imports the open pull requests
   through `fpl:review:import` first.
3. Review written in Radicle that the forge should show: load `fpl:review:export`, dry-run,
   then post.
4. A pull request's forge comments into Radicle without the page: load `fpl:review:import`.

This routine lands nothing; the lander does. Exit codes are those of the sub-skill.
