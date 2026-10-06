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

event="$(cat)"
path="$(printf '%s' "$event" | python3 -c 'import sys,json
try: print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))
except Exception: print("")')"

[ -n "$path" ] || exit 0

case "$path" in
*/docs/DESIGN.md|docs/DESIGN.md|*/docs/SPEC.md|docs/SPEC.md|*/features/*/spec.md|*/features/*/examples/*)
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
