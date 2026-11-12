---
name: fpl:present:silent
description: Ask the forge whether the maintainer has begun to read a pull request, with scripts/present silent. Use before you rewrite, re-present, rebase or force-push a pull-request branch, and whenever you need to know whether psjg has reviewed or commented on one.
---

A pull-request branch is rewritten only while the maintainer is silent on it. Ask the forge
first, every time:

    scripts/present silent N

It reads pull request N as the machine account (reviews, review comments, the conversation,
and the comments on each of its commits, line-level ones included) and prints each URL of
his, one a line.

- **Exit 0**: he is silent. Rewrite, then run it again just before the push, since his word
  may come while you build.
- **Exit 1**: he has spoken. Leave the commits he may have read as they are: present the
  history as built and put a fix on top. Go on only when every URL printed is a comment of his
  that asks for this rewrite; it is then the rewrite's brief, and the review card names it.
- **Exit 2**: the forge could not be asked. The message names the rule and the remedy; fix
  the cause and ask again. A failed check is a stop.

The script is the one spelling of this question: it takes the token on a line of its own,
pins every call to github.com, and leaves aside the one workflow line posted with his token
that is not his word.

The full presenter brief, from work tip to review card, is `.claude/agents/presenter.md`.
