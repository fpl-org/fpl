---
name: fpl:series:restack
description: Rebase the current stack onto the latest base, every branch ref of the stack moving with it, with the restack script in this skill's scripts/. Use when main moved under a branch nothing is approved on yet, or after amending a lower commit; never under an approved pull request.
---

    .agents/skills/fpl:series:restack/scripts/restack              fetch, rebase onto main's upstream
    .agents/skills/fpl:series:restack/scripts/restack <base>       another base branch
    .agents/skills/fpl:series:restack/scripts/restack --continue   after resolving conflicts
    .agents/skills/fpl:series:restack/scripts/restack --abort

It fetches the remote the base tracks (remotes are named after the place, `github`; the script
assumes no name), then `git rebase --update-refs <upstream>`, so every stack ref pointing into
the range, the pull-request branches among them, moves along; `rerere` replays an earlier
conflict resolution. Only where nothing is approved yet (`.agents/WORKFLOW.md`, rule 10): a
restack rewrites every branch above the commit it changes, so a change under an approved pull
request would rebase that one too. Fix forward there; above the highest approved pull request
the stack is yours, with that branch as the base. A frozen stack does not follow `main`
around; only a real conflict asks for a rebase, and the lander relocates a head on its own
(`land/ancestor`: restack before approval, never after).

- **Exit 0**: on top of the upstream; the refs that moved are listed. Or nothing to do.
- **Exit 1**: detached HEAD (check out the stack branch), or the base tracks no upstream
  (`git branch -u <remote>/<base> <base>`).
- **A conflict**: git's own exit; resolve, `git add`, then `--continue`, or `--abort`.

A branch checked out in another worktree does not move: `--update-refs` leaves it on the old
commits. Switch that worktree off it first (`git worktree list` shows where).

To amend a commit that is not on top: `git rebase -i --update-refs github/main`, before it is
approved. The same with `jj`: `.agents/JJ.md`.
