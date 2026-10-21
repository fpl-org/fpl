---
name: fpl:land:land
description: Fast-forward main to an approved head, with scripts/land or the land workflow. Use after a clean dry run; the push is the maintainer's or the lander's, never an agent's, and the merge button is never used.
---

Two ways, after `fpl:land:dry-run` printed no `NO`:

- The lander: `gh workflow run land.yml --repo github.com/fpl-org/fpl --ref main -f pr=<n>`
  (or Actions, land, Run workflow). It judges the same rules plus `land/ci` and
  `land/autodelete`, writes the `fpl/series` check run, fast-forwards `main`, retargets what
  is stacked on the branch and deletes it if still at the landed head.
- The maintainer: `scripts/land <number>` prints the conversation, opens the diff, waits for
  Enter, checks everything again and pushes `<head>:refs/heads/main` without force. Only he
  can; an agent that is asked runs the dry run and reports.

After either: `git fetch github`; `github/main` is the landed head and the branches above
need no restack. A `LOUD` line after the push means the forge does not show what was
expected (`main` not the head, no merge shown, a rule changed): read it, undo nothing by
hand. A range touching `.github/workflows` lands by the owner's deploy key
(`land/workflows`): `fpl:land:by-hand`.
