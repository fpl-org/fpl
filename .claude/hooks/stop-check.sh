#!/usr/bin/env bash
#
# .claude/hooks/stop-check.sh — Stop hook. Best-effort, never fails the turn.
#
# Only does anything inside an implementation worktree (one that has an `fpl/`
# dir). There it applies the safe fixes and runs the quick lane (quality/noslop.mk),
# so the tree does not drift away from `make check` green between turns. At the
# harness root it is a no-op.

set -uo pipefail

root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[ -n "$root" ] || exit 0
[ -d "$root/fpl" ] || exit 0

cd "$root"
[ -f Makefile ] || exit 0
make -s fix >/dev/null 2>&1 || true
make -s quick 2>&1 | tail -n 5 || true

exit 0
