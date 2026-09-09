---
description: Read-only check that the implementation matches every features/*/spec.md
---

Report drift between the code and the maintainer-authored specs. **Read-only** — make no
edits, open no PRs.

1. For each `features/<name>/spec.md`: read it, then read the relevant parts of
   `fpl/grammar.lark`, `fpl/desugar.py`, `fpl/eval.py`, `fpl/types.py`.
2. For every claim in the spec (a syntax form, a desugaring, a semantic rule, an error),
   state: **matches** / **diverges** / **unimplemented**, each with a `file:line` anchor.
3. Run `make check` and note any red.
4. Summarise: is the implementation faithful to the specs? List each divergence as its own
   line with the spec sentence, the code anchor, and which side looks wrong.
5. Do not fix anything. Hand the list to the maintainer.
