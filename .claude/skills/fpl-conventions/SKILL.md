---
name: fpl-conventions
description: The FPL repo's layout, commit convention, and stacked-commit workflow. Use before implementing an FPL feature, scaffolding a worktree, or making a commit in this repo.
---

The canonical rules live in `docs/`. This skill just loads them so a Claude session follows
the same conventions any agent would. Read, in order:

1. **`AGENTS.md`** — what the repo is, the worktree model, the settled stack, the `make check`
   gate, the oracle rule.
2. **`.agents/CONVENTIONS.md`** — the `bootstrap/fpl/` module tree (surface AST → desugar → core AST →
   semantics; spans on every node; no semantics in `parse.py`), the `fpl/features/` +
   conformance layout, `.expected` format, `make check` composition, the ambiguity gate.
3. **`.agents/COMMITS.md`** — Conventional-Commits header + the git-trailer provenance block,
   the machine-account authorship model, `[gate]` vs `[advisory]` rules. Commit with
   `scripts/acommit`.
4. **`.agents/WORKFLOW.md`** — stacked commits: base → stack → restack → land; `scripts/restack`.
5. **`.agents/STACK.md`** — why the stack is what it is; do not reopen it.

Key don'ts: never edit a `fpl/features/*/spec.md`, `docs/DESIGN.md`, or `docs/SPEC.md` (the
oracle — hooks enforce this); never invent language semantics not in a spec; never report a
feature done on a red or unrun `make check`.
