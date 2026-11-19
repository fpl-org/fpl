#!/usr/bin/env bash
#
# .claude/hooks/guard-specs.sh — PreToolUse(Edit|Write) guard for the oracle rule.
#
# Blocks edits to the maintainer-authored spec files and examples (the .fpl
# programs and their .expected output) unless the session has
# explicitly opted in with  FPL_SPEC_EDIT=1  (the /design-fpl command sets it).
# This is the Claude-session mirror of the [spec]-marker check in
# .githooks/commit-msg; see .agents/COMMITS.md and AGENTS.md ("oracle rule").
#
# Hook contract: reads a JSON event on stdin; exit 2 blocks the tool call and
# feeds stderr back to the model. Any other exit lets it through.

set -euo pipefail

# The guard runs under scripts/deadline (step claude.guard-specs, scripts/deadlines.tsv). A guard
# that cannot decide in time (a python3 that waits on something) blocks the edit, as does a runner
# that cannot bound it, or a runner (or guard) that cannot be run at all (126, 127): exit 2, with
# the runner's or the shell's line as the reason the model reads.
if [ "${FPL_DEADLINE_STEP:-}" != claude.guard-specs ]; then
	rc=0
	"${0%/*}/../../scripts/deadline" claude.guard-specs -- "$0" "$@" || rc=$?
	case "$rc" in 124 | 125 | 126 | 127) exit 2 ;; esac
	exit "$rc"
fi

event="$(cat)"
path="$(printf '%s' "$event" | python3 -c 'import sys,json
try: print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))
except Exception: print("")')"

[ -n "$path" ] || exit 0

case "$path" in
*/docs/DESIGN.md|docs/DESIGN.md|*/docs/SPEC.md|docs/SPEC.md|*/fpl/features/*/spec.md|fpl/features/*/spec.md|*/fpl/features/*/examples/*|fpl/features/*/examples/*)
	if [ "${FPL_SPEC_EDIT:-0}" = "1" ]; then
		exit 0
	fi
	echo "guard-specs: '$path' is a maintainer-authored spec (the oracle)." >&2
	echo "            Agents implement against it, they do not edit it." >&2
	echo "            If this edit is genuinely intended, rerun with FPL_SPEC_EDIT=1" >&2
	echo "            and commit with the [spec] marker (see .agents/COMMITS.md)." >&2
	exit 2
	;;
esac

exit 0
