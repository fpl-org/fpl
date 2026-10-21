---
name: fpl:commit
description: Make one commit the way every gate of this repository wants it, with scripts/acommit. Use whenever you are about to commit, in a terminal session or as the GitHub App; it runs the sub-skills identity, acommit, lint and boundary in that order.
---

A commit here is authored by the machine account, carries the model and the session as
trailers, changes one side of the tree, and passes `.githooks/commit-msg`. The rules and why
they hold: `.agents/COMMITS.md`. This routine is the order of work; each step is a sub-skill.

1. **Identity**, once per worktree: load `fpl:commit:identity`. `.git/agent-identity` holds
   the machine account's address, or acommit refuses.
2. **Message and commit**: load `fpl:commit:acommit`. Stage at hunk level, one logical change;
   the summary is imperative and lower-case, the body says why, the trailers come from the
   options and the environment. Never a bare `git commit`: the hook refuses a message without
   the trailers, and `--no-verify` is caught at the push.
3. **Lint**, before a push or a presentation: load `fpl:commit:lint` over the range the push
   adds. Every FAIL names a rule and its remedy; fix the commit (amend, or `rebase -i`) and
   lint again.
4. **Boundary**: a `BOUNDARY-MIXED` refusal from the lint means one commit touched harness and
   implementation paths. Load `fpl:commit:boundary` to split it in two.

A new branch name goes through `fpl:commit:branch` before the branch exists. A series that
is about to be reviewed gets its identity, the `Series-Id:` trailer, from the series module.
