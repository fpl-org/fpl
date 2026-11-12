---
name: fpl:pr:open
description: File the pull request of a pushed agent branch as the machine account, with .agents/skills/fpl:pr/scripts/pr. Use once the branch is on the forge at the commit you have; opens a draft on main, or on the branch of an open pull request with -B.
---

    .agents/skills/fpl:pr/scripts/pr --draft [-B <parent>] [-t <title>] [--body-file <f>] [<branch>]

The current branch when none is named. Title and body come from the first commit (with more
than one, every subject is listed), or from `-t`, `-b`, `--body-file`; the text goes through
the leak gate first. `-n` prints what would be sent and sends nothing. Without `--draft` the
pull request opens ready, which asks the maintainer at once: only for work no bot is to read
first. `-B <parent>` stacks on the head branch of an open pull request; the branch must be
built on it, and the remedy printed is the rebase that gets it there.

- **Exit 0**: the URL on stdout, and nothing else; a branch already open prints that one.
- **Exit 1**: not pushed, or the forge has another commit (push first, with the token URL from
  `fpl:pr:whoami`); the token is not the machine account's (`.git/agent-credentials`,
  `.agents/WORKFLOW.md`, The agent's credential); not an agent branch; the parent is not an
  open pull request; a private term in the text. The message says which.
