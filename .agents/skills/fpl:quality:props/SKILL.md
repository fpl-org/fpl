---
name: fpl:quality:props
description: Check that every module with code has a Hypothesis property test and pays its metatheory obligations, with .agents/skills/fpl:quality:props/scripts/props. Use when make check fails at the props step, or when adding a module or an obligation.
---

`make check` runs it in `bootstrap/` with `--obligations ../quality/obligations.toml`. Without
arguments it judges the repository's own `bootstrap/fpl`, `bootstrap/tests` and
`quality/obligations.toml`, found from the script, so it means the same from anywhere; by
hand, from the root:

    .venv/bin/python .agents/skills/fpl:quality:props/scripts/props \
        [--source DIR] [--tests DIR] [--obligations FILE]

A path given is read from the directory it runs in.

A module of the package that defines anything needs at least one test file that imports it
and holds a `@given` test. An obligation listed for the module in `quality/obligations.toml`
is paid by a test that names it:

    @pytest.mark.obligation("desugaring preserves meaning")

- **Exit 0**: every module has a property test and every obligation is paid.
- **Exit 1**: a module without one, or an obligation no test names; each is listed. Write the
  test; which properties to state is the author's call, that there is one is not.
- **Exit 2**: usage, or an input path that is missing (never an empty scan).

`--self-test` runs the built-in fixtures; `make gates` runs it through the header line. Which
obligations exist and why: `.agents/QUALITY.md`, "Properties" and "Metatheory".
