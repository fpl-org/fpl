---
name: fpl:quality:diagrams
description: Draw the map of the code, its import graph with import-linter's verdicts and a class diagram per module, as Mermaid, with scripts/diagrams. Use when asked for the architecture or layering of the walker, or to see what a pull request moves.
---

A view, not a check; nothing in `make check` depends on it:

    make map                                   # from the root: into .noslop/map/
    .venv/bin/python scripts/diagrams [--root DIR] [--source DIR] [--out DIR]

It draws the root package `quality/importlinter.ini` names, found in the directory the
script's `SOURCE` names, with import-linter's verdict on each contract of that file (the same
verdict `lint-imports` gives in `make check`) and a class diagram per module. The output is
never committed: computed from the code each time, it cannot go stale.
`.github/workflows/map.yml` draws the head and the base of every pull request into the
run's summary, with the difference between the two; that workflow names `scripts/diagrams`
by path, so the script stays in `scripts/`.

- **Exit 0**: the map is in `--out`; read `.noslop/map/*.md`.
- **Exit 1**: the self-test failed.
- **Exit 2**: usage, or no contracts: the package or `importlinter.ini` is not where `--root`
  or `--source` say.

`--self-test` draws a built-in package; `make gates` runs it through the header line.
