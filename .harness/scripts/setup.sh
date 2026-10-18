#!/usr/bin/env bash
#
# .harness/scripts/setup.sh — make a clone or worktree ready for the FPL commit workflow.
#
# Idempotent. Run it once after `git clone`, and once inside every new worktree
# (`.harness/scripts/new-worktree.sh` / `.claude/commands/new-worktree.md` call it for you).
#
# What it does:
#   1. Points git at the tracked hooks in .githooks/ (so prepare-commit-msg, commit-msg and
#      pre-commit run) and reports which of them git will run.
#   2. Turns on the three settings the stacked-commit workflow in .agents/WORKFLOW.md
#      relies on: --update-refs by default, rerere (remember conflict resolutions),
#      and scissors cleanup (so the rules the commit template carries, which
#      prepare-commit-msg writes below git's scissors line, never reach a commit).
#   3. Reports whether the agent author identity (.git/agent-identity) is set;
#      see .agents/COMMITS.md for why it exists and `.harness/scripts/agent-identity.sh` to set it.
#
# It never writes anything outside `git config --local` and never commits.

set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

echo "==> git config (local)"
git config --local core.hooksPath .githooks
git config --local rebase.updateRefs true
git config --local rerere.enabled true
git config --local rerere.autoUpdate true
git config --local commit.cleanup scissors
echo "    core.hooksPath      = $(git config --local core.hooksPath)"
echo "    rebase.updateRefs   = $(git config --local rebase.updateRefs)"
echo "    rerere.enabled      = $(git config --local rerere.enabled)"
echo "    commit.cleanup      = $(git config --local commit.cleanup)"

echo "==> hooks (.githooks/, through core.hooksPath)"
for hook in pre-commit prepare-commit-msg commit-msg pre-push reference-transaction; do
	if [ -x ".githooks/$hook" ]; then
		echo "    $hook"
	elif [ -e ".githooks/$hook" ]; then
		echo "    $hook is not executable, so git ignores it: chmod +x .githooks/$hook"
	fi
done

echo "==> agent author identity"
if id_email="$("$repo_root/.harness/scripts/agent-identity.sh" show 2>/dev/null)"; then
	echo "    set: $id_email"
else
	cat <<-'EOF'
	    NOT SET. Agent commits via .harness/scripts/acommit.sh will refuse until you run:

	        .harness/scripts/agent-identity.sh set "<id>+psjg-claude@users.noreply.github.com"

	    (the noreply address of the GitHub machine account — see .agents/COMMITS.md).
	    Human-only commits are unaffected.
	EOF
fi

echo "==> done"
