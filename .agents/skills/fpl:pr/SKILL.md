---
name: fpl:pr
description: The pull request of an agent branch, from the push to the maintainer's review, with .agents/skills/fpl:pr/scripts/pr. Use when a branch is built and pushed and needs a pull request, a body, to leave draft, or a reviewer; the routine loads one sub-skill per step.
---

A pull request is filed by the machine account, on `main`, as a draft; the maintainer reads it
once it is ready, and nothing before that may ask him (`.agents/WORKFLOW.md`, The rules). The
script is `.agents/skills/fpl:pr/scripts/pr`, run from the repository root; it reads refs and
the forge, never the working tree, and does not push. The steps, each its own skill:

1. `fpl:pr:whoami`: which account a push from here goes out as; push with the token URL it names.
2. `fpl:pr:open`: file the draft (`pr --draft`), or stack it on an open pull request (`-B`).
3. `fpl:pr:body`: the review card as the body (`pr --update-body`), through the leak gate.
4. `fpl:pr:ready`: out of draft once the bots are quiet (`pr --ready`).
5. `fpl:pr:reviewer`: a further reader, by login (`pr --reviewer`).

`fpl:pr:tree` draws the open pull requests as the tree of their bases. A finished branch is
presented before step 3, by the presenter routine (pull request 200; until it lands,
`.claude/agents/presenter.md`). Every refusal of `pr` exits 1 and names what to do; exit 0
prints the URL (open) or a line on stderr (the rest).
