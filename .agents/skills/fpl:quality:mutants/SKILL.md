---
name: fpl:quality:mutants
description: Run mutation testing and give a verdict on every mutant that lived, with .agents/skills/fpl:quality:mutants/scripts/mutants. Use when make harden fails at the mutants step, or when a survivor needs an entry in bootstrap/mutants.allow.
---

`make harden` runs it last, in `bootstrap/`, where mutmut works and `mutants.allow` is
read. By hand, from there:

    ../.venv/bin/python ../.agents/skills/fpl:quality:mutants/scripts/mutants [--judge]

mutmut changes the code one small way at a time and runs the tests against each change. A
mutant the tests do not catch survived: that line runs, but nothing checks what it does.
`--judge` skips `mutmut run` and judges the last run's results again, as after an edit of
`mutants.allow`.

- **Exit 0**: every mutant killed, or allowed in `mutants.allow`. An entry for a mutant that
  no longer lives is reported, so the file can shrink, and does not fail the run.
- **Exit 1**: a `mutmut run` that failed (the clean test run must pass first), or one that
  found no mutants at all; a mutant that survived, timed out, or had no test; an allow entry
  without a reason. Write the test that kills the mutant; only an equivalent one, which no
  test could tell apart, goes in the file, one per line with its reason:

      fpl.parse.x_where__mutmut_3 -- equivalent: column 0 and column 1 print the same caret

- **Exit 2**: usage.

`mutants.allow` is policy: the commit carries `[policy]` and touches no code. Minutes per run.
`--self-test` exercises the verdicts without mutmut; `make gates` runs it through the header
line. Why mutants: `.agents/QUALITY.md`, "Mutants".
