---
name: fpl:quality:escapes
description: Refuse a checker waiver that does not name its rule and give a reason, with scripts/escapes. Use when make check or make tools fails at the escapes step, or before writing a noqa, type-ignore, pyright-ignore or no-cover comment.
---

`make check` runs it in `bootstrap/` on `fpl tests`, `make tools` on each tool's package and
tests. Without arguments it scans the repository's own `bootstrap/fpl` and `bootstrap/tests`,
found from the script, so it means the same from anywhere; by hand, from the root:

    .venv/bin/python scripts/escapes [<dir>...]

A directory given is read from where it runs. The script stays in `scripts/` because
`.github/workflows/tools.yml` names that path.

Every way out of a check carries the rule it waives and, after ` -- `, why:

    # noqa: E731 -- <reason>
    # pyright: ignore[reportUnknownMemberType] -- <reason>
    # type: ignore[arg-type] -- <reason>
    # pragma: no cover -- <reason>

`# type: ignore` waives mypy alone (pyright does not honour it), so a line both refuse carries
two waivers, each reasoned.

- **Exit 0**: no bare waiver.
- **Exit 1**: each bare one, with file and line. Name the rule and say why, or fix the code.
- **Exit 2**: usage, or a path that is not a directory.

`--self-test` runs the built-in cases; `make gates` runs it through the header line.
