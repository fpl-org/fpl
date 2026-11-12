---
name: fpl:land:by-hand
description: Walk a step of filing, presenting, checking or landing a pull request without the scripts, with git, gh and the browser. Use when a script fails and the step must still be made, or to see what a script does before trusting it.
---

Every step the scripts take has a route a person can walk, so the pipeline is never the only
way through. The recipes are in `.agents/WORKFLOW.md`, By hand, one block per step:

- **Open a draft**: push with the token in the URL and the helper list emptied, then
  `gh pr create --draft --base main`, the card as the body.
- **Present**: `series stamp`, a tag for W, rewrite, `git diff --quiet` and
  `git rebase --exec 'make quick'` as the proof, a force-push under lease.
- **Manifest**: the patch ids and message hashes, and their digest, as `series` does.
- **Ready and approve**: `gh pr ready`; he approves in the UI; `gh api .../reviews` shows the
  SHA the approval names.
- **Check**: `scripts/land --dry-run` (`fpl:land:dry-run`); it is the by-hand check too.
- **Land**: dispatch the lander, or the owner's deploy key for a range that touches
  `.github/workflows`: `git push git@github-fpl-deploy:fpl-org/fpl.git <head>:refs/heads/main`,
  then the retargets and the branch deletion under lease.
- **Relocate**, **Revert a series**: carry commits over unchanged, or undo a contiguous range.

A landing by hand writes no `fpl/series` receipt; every `gh` command names `github.com`.
