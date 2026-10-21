---
name: fpl:quality:crap
description: Score every function's CRAP (complexity against coverage) and refuse the worst, with .agents/skills/fpl:quality:crap/scripts/crap. Use when make check fails at the crap step, or to see which functions are complex and untested.
---

`make check` runs it after the coverage run, in `bootstrap/`, where that run leaves its
report. By hand, from there, with the root's `.venv`:

    ../.venv/bin/python ../.agents/skills/fpl:quality:crap/scripts/crap \
        --policy ../quality/crap.toml [--coverage .noslop/coverage.json] [--source fpl]

Its paths are read from the directory it runs in; the defaults shown are `bootstrap/`'s.

CRAP(m) = C²(1 − p)³ + C: C is radon's cyclomatic complexity of the function, p the share of
its lines and branch destinations the tests ran, read from coverage.py's JSON report, which
must exist (run the coverage lane first). `quality/crap.toml` holds `max`, 8 today; changing
it is `[policy]`.

- **Exit 0**: every function within the limit. The report also lists one-call wrappers:
  counted, never refused, so splitting a function into relays gains nothing (`.agents/QUALITY.md`).
- **Exit 1**: a function over the limit, or one the coverage report does not know, named
  with its score. Test the function, or make it smaller; do not raise `max`.
- **Exit 2**: usage.

`--self-test` runs it on a built-in fixture; `make gates` runs that through its header line.
Why the score and where it comes from: `.agents/QUALITY.md`, "CRAP".
