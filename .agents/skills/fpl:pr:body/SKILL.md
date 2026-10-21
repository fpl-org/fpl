---
name: fpl:pr:body
description: Replace the body of an open pull request with a file, through the leak gate, with .agents/skills/fpl:pr/scripts/pr --update-body. Use to put the review card on a pull request, or to correct a body; never paste a body into the forge by hand.
---

    .agents/skills/fpl:pr/scripts/pr --update-body <number> <file>

The file is the body, whole: write it as the review card (`.agents/REVIEW-CARD.md`, the
headings `land/card` wants), through `leak-check --text` first. The script copies the
file, judges the copy and sends that copy, so a writer racing the request cannot slip text
past the gate. The generated body of `fpl:pr:open` ends with the line
`landing: fast-forward by the lander after review.`; keep it, or let the card say so.

- **Exit 0**: `pr: body of #<n> replaced` on stderr.
- **Exit 1**: a private term (`nothing was sent`), an unreadable file, or the token is not the
  machine account's. Fix the text, not the gate (`FPL_LEAK_GATE=warn` is for a false refusal
  you can name).
