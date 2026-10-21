---
name: fpl:land
description: Land an approved pull request on main by fast-forward, with scripts/land. Use once the maintainer has approved the exact head; the routine is a dry run, then the landing, and the by-hand route when the scripts cannot.
---

Landing is a fast-forward of `main` to the approved head: the commits reviewed are the
commits landed, SHAs and all, so nothing stacked above moves. The merge button, a squash or
a local merge is never used; an approved pull request is frozen (`.agents/WORKFLOW.md`, The
rules). The maintainer's side of the review is the maintainer's: an agent runs the dry run and
reports; the landing is his, or the lander workflow's.

1. `fpl:land:dry-run`: every rule, the push it would make, nothing changed.
2. `fpl:land:land`: the push, by the owner or the lander; then the retargets it prints.
3. `fpl:land:by-hand`: when a script fails, each step as plain git and `gh`.

A stack lands bottom first, one pull request at a time; the tree of open pull requests,
their bases drawn, shows the order.
`scripts/land` exits 0 when every rule holds (and, landing, `main` is the head), 1 on a
refusal, naming the rule and the remedy, 2 on a usage error.
