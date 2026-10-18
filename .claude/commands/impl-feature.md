---
description: Implement a feature until make check is green, never touching its spec
argument-hint: <name>
---

Implement `03-fpl/03.01-features/$1/` (fixtures already written by the maintainer). Rules from `AGENTS.md`
and `.agents/CONVENTIONS.md`:

1. Read `03-fpl/03.01-features/$1/spec.md` and every `examples/*.fpl` + `*.expected`. If `spec.md` is still
   a stub, stop and ask the maintainer to write it — do not guess semantics.
2. `make check` should be **red** now (new conformance cases fail). Confirm that.
3. Implement across `01-bootstrap/fpl/grammar.lark` → `01-bootstrap/fpl/desugar.py` → (only if unavoidable)
   `01-bootstrap/fpl/ast_core.py` / `01-bootstrap/fpl/eval.py`. Keep the core AST small; a new core node is a design
   decision — surface it to the maintainer, don't just add one.
4. Keep `pyright` strict-clean and the ambiguity test green throughout.
5. **Never edit `03-fpl/03.01-features/$1/spec.md`** (the guard-specs hook and `.githooks/commit-msg`
   enforce this). If the spec looks wrong, say so and let the maintainer decide.
6. When `make check` is green, commit the work as a small stack (`.agents/WORKFLOW.md`) with
   `.harness/scripts/acommit.sh`. Then run `/spec-check`.
