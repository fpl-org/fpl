---
name: fpl:quality:gates
description: Prove that each check of the gate still refuses its bad example, with .agents/skills/fpl:quality:gates/scripts/gates, and add a case or a self-test for a new check. Use after any change under quality/ or scripts/, or when make gates fails.
---

`make gates` (from the root: `make -f quality/noslop.mk gates`) runs three things, in order:

1. ruff over the harness's own Python, the files `scripts/gates-list --lint` prints;
2. every tool's self-test, the commands `scripts/gates-list` prints, in file-name order;
3. this script, last by rule, in the root's `.venv`:

       .venv/bin/python .agents/skills/fpl:quality:gates/scripts/gates [<case>...]

For each `quality/bad/<case>/` it lays the harness (`quality/`, `scripts/`, `.agents/skills/`)
and the fixture project `quality/bad/_base/` into a temporary directory, runs `case.toml`'s
`run` there once as the control, which must pass, then with the case's files laid over,
which must fail and print `expect`.

- **Exit 0**: every case refused its bad example.
- **Exit 1**: a case let it through, failed without the expected text, or failed on the
  control alone (then the case proves nothing). Fix the check, or the case.
- **Exit 2**: a case name that does not exist.

A new check adds its case, and its proof as a file, never a line in `noslop.mk`: an
executable `scripts/<name>-self-test`, or one header line in the tool,
`# gates: $BIN/python $ROOT/.agents/skills/<skill>/scripts/<name> --self-test`
(`$S` for a tool still in `scripts/`). `gates-list` refuses a line it would not read.
Why a control run: `.agents/QUALITY.md`, "Proof that the checks bite".
