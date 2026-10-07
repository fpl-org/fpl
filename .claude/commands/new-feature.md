---
description: Scaffold fpl/features/<name>/ then stop for the maintainer to write the fixtures
argument-hint: <name>
---

Scaffold a feature directory, then hand back to the maintainer. See the oracle rule in
`AGENTS.md` and the layout in `.agents/CONVENTIONS.md`.

Given `$1` = feature name (inside an implementation worktree):

1. Copy `fpl/features/_template/` to `fpl/features/$1/`.
2. Leave `spec.md`, `examples/*.fpl`, and `examples/*.expected` as the template stubs.
3. **Stop.** Print exactly what the maintainer must fill in:
   - `fpl/features/$1/spec.md` — surface syntax, desugaring, semantics
   - `fpl/features/$1/examples/*.fpl` — programs exercising it
   - `fpl/features/$1/examples/*.expected` — expected stdout, or `ERROR: <line>:<col> <message>`
4. Do **not** write any of those files yourself — they are the oracle. Do not start
   implementing. `/impl-feature` continues once the maintainer has written the fixtures.
