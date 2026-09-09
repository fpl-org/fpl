#!/usr/bin/env bash
#
# .claude/hooks/stop-check.sh — Stop hook. Best-effort, never fails the turn.
#
# Only does anything inside an implementation worktree (one that has an `fpl/`
# dir). There it formats and quickly tests, so the tree does not drift away from
# `make check` green between turns. At the harness root it is a no-op.

set -uo pipefail

root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[ -n "$root" ] || exit 0
[ -d "$root/fpl" ] || exit 0

cd "$root"
command -v ruff >/dev/null 2>&1 && ruff format --quiet fpl tests 2>/dev/null || true
command -v pytest >/dev/null 2>&1 && pytest -q --no-header -x 2>&1 | tail -n 5 || true

exit 0
