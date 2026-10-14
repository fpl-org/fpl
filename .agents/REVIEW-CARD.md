# REVIEW-CARD.md: the body of a pull request

The presenter (`.claude/agents/presenter.md`) writes it from this template: English, at most 40
lines, through `scripts/leak-check --text`. Fill each `<...>`, keep the headings and the order.

Written by an AI agent (<model>) working for @psjg, as presenter of this pull request.

## What
<Two to four sentences: the change, and why, in the words of the decision it serves.>

## What changes
- Before: <what a user or agent met>. After: <what they meet now>.
- Now possible: <...>
- Now refused: <...>
- Still waiting: <what this leaves for a later series>
- Size: <n> commits, <f> files, +<a> / -<d>.

<Only when the behaviour shows in the REPL: a fenced transcript, input and output, at most 8
lines. Otherwise drop this paragraph.>

## How checked
- Gates: <present-check or make gates, its result, on which head>.
- Bots: <CodeRabbit, Codex, Claude review: each finding, and applied or rejected with why>.
- GPT verification: <findings as a list, each applied or rejected with why; its text never lands>.

## Limits
- <what is not done, not checked, or known to be wrong>

## Verdict
<One line: merge, merge after <x>, or do not merge, and why.>

Series-Id: <id, or n/a until scripts/series is on main>
Digest: <the digest of scripts/series manifest base..head, or n/a>

| # | commit | lemma |
| --- | --- | --- |
| 1 | <short sha> | <subject> |
