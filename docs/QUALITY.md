# QUALITY.md — the noslop gate

An implementation worktree is done when `make check` is green (AGENTS.md). This file says what
that gate runs, why each check is in it, and how its strictness is kept out of reach of the
code it judges. The harness side lives in `quality/` and `scripts/`; a worktree's `Makefile` is
one line, `include quality/noslop.mk`.

The checks are aimed at the ways agent-written code goes wrong without failing a test: code
nobody runs, tests that run code without checking it, branches that pile up, layers that leak
into each other, and quiet waivers. Several come from Robert C. Martin's 2026 practice of
putting agents under CRAP, mutation testing and dependency rules; the rest are the standard
Python tools for the same jobs.

## The lanes

```
make fix      ruff's safe fixes, then the formatter
make quick    lint, format, tests; stops at the first failure. Seconds. The inner loop.
make check    the one gate. Green means done.
make harden   check, then the long search: 20x the examples, CrossHair, mutation testing
make ready    harden, then a known-vulnerability audit of the pinned tools
make gates    proof that each check still refuses a bad example
```

`make check` runs, in order:

| Check | Refuses |
| --- | --- |
| `pristine` | an uncommitted change to a policy file (below) |
| `ruff check`, `ruff format --check` | lint findings, including cyclomatic complexity over 8 (`quality/ruff.toml`); unformatted code |
| `pyright`, strict | anything strict mode refuses, and a `match` that misses a case (`quality/pyright.json`) |
| `scripts/escapes` | a waiver that does not name its rule and give a reason |
| `scripts/props` | a module with code that no property test imports |
| `pytest` under `coverage` | a failing test; less than 100% line and branch coverage (`quality/coveragerc`) |
| `scripts/crap` | a function whose CRAP score is over 8 (`quality/crap.toml`) |
| `lint-imports` | an import that crosses the layering of CONVENTIONS.md (`quality/importlinter.ini`) |
| `deptry` | an import of a package `pyproject.toml` does not declare, or a declared one nobody imports |
| `vulture` | code nothing uses |
| `pylint` duplicate-code | six or more lines repeated |

On the milestone-0 skeleton `make check` takes about 6 seconds and `make harden` about 2½
minutes, almost all of it CrossHair.

## CRAP

CRAP(m) = C²(1 − p)³ + C, with C the cyclomatic complexity of function m and p the share of its
lines and branches the tests run. `scripts/crap` computes it from radon's complexity and
coverage.py's branch data, counting only a function's body, since its `def` line runs on
import. A function over 8 fails, and so does one the coverage report does not know.

With coverage at 100% CRAP equals C, so in practice the limit is a complexity limit of 8, which
ruff also enforces. The CRAP gate matters when coverage slips, and even then it is lenient:
complexity 5 with four of its branches untested scores 7.6 and passes. Coverage at 100% is what
bites first. Martin found that a hard complexity limit makes an agent split functions into
pieces that only pass their arguments along; `scripts/crap` counts those one-call wrappers in
its report, and does not refuse them.

## Properties

Every module with code needs a test that imports it and uses Hypothesis's `@given`. Which
properties it states is the author's to judge; that there is one is not optional. The profiles
are in `quality/noslop_pytest.py`, loaded by every test run:

- `quick`, 100 examples per property: `make quick` and `make check`.
- `harden`, 2000 examples: `make harden`.
- `symbolic`, the same properties handed to CrossHair, which solves for inputs that reach each
  branch instead of drawing them at random: `make harden`. 50 examples; CrossHair spends up to
  2.5 s per path, so a property that runs deep into Lark costs most of the budget.

On Linux, CrossHair's solver needs libstdc++ on the loader path; the dev shell sets it
(docs/DEVSHELL.md), and `make harden` stops with a message if it does not load.

## Mutants

`scripts/mutants` runs mutmut: it changes the code one small way at a time (`<` to `<=`, a
string to another, an argument to `None`) and runs the tests against each change. A mutant the
tests do not catch has survived: the line it changed runs, but nothing checks what it does.
Every mutant that is not killed fails `make harden`, unless `mutants.allow` in the worktree names
it with a reason:

```
fpl.parse.x_where__mutmut_3 -- equivalent: column 0 and column 1 print the same caret
```

The file is for equivalent mutants, which no test can kill. An entry without a reason is
refused; one whose mutant no longer lives is reported. A run that lists no mutants at all fails.

## Waivers

Every way out of a check names what it waives and says why, after ` -- `:

```
# noqa: E731 -- <reason>
# pyright: ignore[reportUnknownMemberType] -- <reason>
# pragma: no cover -- <reason>
```

`# type: ignore` is refused outright, since pyright's own form names the rule.

## Policy

The gate is only as strict as the files that configure it, and an agent that can edit them in
the same commit as its code can make any code pass. So:

- `quality/` and `scripts/` are harness. A worktree commit may not touch them
  (`.githooks/pre-commit`); they change from the root, like the rest of the harness.
- `quality/`, `pyproject.toml`, `Makefile` and `mutants.allow` are policy. A commit that
  changes one carries the marker `[policy]` in its message and touches neither `fpl/` nor
  `tests/` (`.githooks/commit-msg`), so the change is reviewed on its own.
- The gate judges only committed policy: `make check` stops when any policy file, or
  `scripts/`, differs from what is committed.
- The examples under `features/*/examples/` are oracle, like `spec.md`: `[spec]` and the
  `guard-specs` hook (AGENTS.md, "The oracle rule").

The tools and their versions are pinned in `quality/uv.lock`. `make` syncs them into the
worktree's `.venv` with `uv sync --frozen` the first time and whenever the lock changes.

## Proof that the checks bite

A check that passes everything looks the same as a check that found nothing. `make gates` runs
the self-tests of the four scripts, then `scripts/gates`: for each case in `quality/bad/`, the
check runs on a small fixture package, where it must pass, and then with the case's bad example
laid over it, where it must fail with a given message. The first run is the control; without
it, a check that fails for an unrelated reason would count as having caught something. Adding a
check means adding its case.
