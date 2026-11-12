---
name: fpl:quality
description: Run the noslop gate in the right order, check then gates then harden, with make. Use when deciding whether an implementation worktree is done, before a pull request leaves draft, and after any change under quality/ or scripts/.
---

One gate, three lanes, run from the root or from `bootstrap/` (the lanes run there; the one
`.venv` is the root's; `.agents/DEVSHELL.md` for the shell). Green means done; nothing else does.

1. **`make quick`** while editing: lint, format, tests, stopping at the first failure. Seconds.
   `make fix` rewrites what ruff can rewrite.
2. **`make check`**: the gate. Its checks, in order, and what each refuses: `.agents/QUALITY.md`.
   Two of them are this skill's own: `fpl:quality:escapes` (every waiver named and reasoned),
   `fpl:quality:props` (every module has a property test and pays its obligations), and a
   third follows the coverage run: `fpl:quality:crap`. It stops when a policy file differs
   from what is committed, so commit policy first, with `[policy]`.
3. **`make gates`** after a change to the harness itself: ruff over the harness's Python, every
   tool's self-test, then the proof that each check still refuses its bad example:
   `fpl:quality:gates`. A harness-only branch runs it from the root,
   `make -f quality/noslop.mk gates`.
4. **`make harden`** before a pull request leaves draft: check, then 20x the examples,
   CrossHair on every property and contract, then `fpl:quality:mutants`. Minutes.
   `make ready` is harden, gates and a known-vulnerability audit together.

`make map` is a view, not a lane: `fpl:quality:diagrams`. The skills' own gate, `skills-cover`,
is `fpl:quality:skills` (unit S1b).

Exit codes are make's: 0 green; anything else is the first failing step, named in the output,
with its remedy. A step that cannot run (no nix, no z3) stops the lane rather than skipping.
