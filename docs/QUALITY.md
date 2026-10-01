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
make harden   check, then the long search: 20x the examples, CrossHair on every property
              and every contract, mutation testing
make ready    harden, then gates, then a known-vulnerability audit of the pinned tools
make gates    proof that each check still refuses a bad example, and the harness's own lint
```

The same lanes run on the forge (`.github/workflows/noslop.yml`): `make check` on every push
to a pull request, `make ready` once it is out of draft and on every push to `main`. A
harness-only branch, which has no code to judge, runs `make gates` from the root instead:
`make -f quality/noslop.mk gates`. The runner enters the dev shell of `flake.nix`, so it judges
with the tools a laptop has.

`make check` runs, in order:

| Check | Refuses |
| --- | --- |
| `pristine` | an uncommitted change to a policy file (below) |
| `ruff check`, `ruff format --check` | lint findings, including cyclomatic complexity over 8 (`quality/ruff.toml`); unformatted code |
| `pyright`, strict | anything strict mode refuses, and a `match` that misses a case (`quality/pyright.json`) |
| `mypy`, strict | the same code as the reference implementation of the typing PEPs reads it, with unreachable code and unused ignores as errors (`quality/mypy.ini`) |
| `scripts/escapes` | a waiver that does not name its rule and give a reason |
| `scripts/props` | a module with code that no property test imports |
| `pytest` under `coverage` | a failing test; less than 100% line and branch coverage (`quality/coveragerc`) |
| `scripts/crap` | a function whose CRAP score is over 8 (`quality/crap.toml`) |
| `lint-imports` | an import that crosses the layering of CONVENTIONS.md (`quality/importlinter.ini`) |
| `deptry` | an import of a package `pyproject.toml` does not declare, or a declared one nobody imports |
| `vulture` | code nothing uses |
| `pylint` duplicate-code | six or more lines repeated |

On the milestone-0 skeleton `make check` takes about 6 seconds and `make harden` about 3
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

## Contracts

A function may state what it needs and what it promises with icontract:

```python
def inside(result: Span, source: str) -> bool:
    ...

@icontract.require(reported)
@icontract.ensure(inside)
def where(source: str, line: int, column: int) -> Span:
```

The predicates are named, typed functions, not lambdas: strict pyright refuses a lambda's
unknown parameters, and a name says what is promised. icontract checks them on every call,
so a test that reaches the function checks its contract too, and mutation testing sees a
contract as another way a mutant gets killed. `make harden` then runs `crosshair check` over
`fpl/` with the icontract kind: for each contract it solves for an input that breaks it, up
to `CONTRACT_SECONDS` of CPU per condition, and reports the call. That is the difference
from a property test: a property is checked on the inputs Hypothesis draws, a contract on
the inputs a solver finds, and `where()` above was refuted at the end of a line before any
test drew that case.

A precondition is part of the contract, not a way out of it: `reported` says what Lark
delivers, so the solver does not spend its budget on positions Lark never gives. It is
tested through the callers that satisfy it.

## Metatheory

A language has properties its implementation must keep. They are stated as properties, under
Hypothesis in `make check` and CrossHair in `make harden`, and each is due from the moment
the module it concerns has code. `quality/obligations.toml` lists them per module;
`scripts/props` fails a module with code whose obligation no property test pays, and a test
pays one by naming it:

```python
@pytest.mark.obligation("desugaring preserves meaning")
@given(programs())
def test_evaluating_the_core_gives_what_the_surface_gives(program: str) -> None:
```

The obligations:

- `parse.py`: every program the grammar derives (`hypothesis.extra.lark.from_lark`) parses
  without an Earley ambiguity, not only the example corpus.
- `desugar.py`: desugaring preserves meaning: evaluating a surface program and evaluating
  its core translation give the same result, for programs derived from the grammar.
- `ast_surface.py` and `ast_core.py`, once there is a printer: print then parse is the
  identity on the AST.
- `types.py`: progress and preservation: a well-typed core term is a value or takes a
  step, and the step keeps its type.
- The backend, when it exists: the interpreter and the compiled program print the same
  output for every conformance example and for derived programs.

These are the tests that make the layered frontend of docs/STACK.md more than a layout. The
two that wait on a module that does not exist yet (a printer, a backend) are noted in the
file and not owed by anyone until it does.

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
# type: ignore[arg-type] -- <reason>
# pragma: no cover -- <reason>
```

`# type: ignore` is mypy's form and waives mypy alone: pyright is configured not to honour it
(`enableTypeIgnoreComments: false`), so a line that both checkers refuse carries two waivers,
each with its reason. A bare `# type: ignore` is refused.

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

A check that passes everything looks the same as a check that found nothing. `make gates` first
holds the harness's own Python (`scripts/crap`, `props`, `escapes`, `mutants`, `gates`,
`forward-only` and the pytest plugin) to the ruff rules it holds others to, then runs the
self-tests of those five scripts and of `scripts/leak-check`, then `scripts/gates`: for each
case in `quality/bad/`, the check runs on a small fixture package, where it must pass, and then
with the case's bad example laid over it, where it must fail with a given message. The first
run is the control; without it, a check that fails for an unrelated reason would count as
having caught something. Adding a check means adding its case.
