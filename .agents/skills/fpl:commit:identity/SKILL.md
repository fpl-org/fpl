---
name: fpl:commit:identity
description: Read or set the author address agent commits carry in this worktree, with scripts/agent-identity. Use once in every new worktree before its first commit, and when acommit refuses for want of an identity.
---

    scripts/agent-identity show             print the address; exit 1 when unset
    scripts/agent-identity set <address>    store it; exit 2 when it is not an address
    scripts/agent-identity path             print the file

The value is one line in `.git/agent-identity`: per worktree, inside the git directory, never
committed. `scripts/acommit` reads it for `--author="<model display name> <address>"`; the
name carries the model, the address is the one machine account, so every model links to one
contributor on the forge. The committer stays whoever runs the session, from their own git
config.

The address is the machine account's, the first line of `.github/agent-emails`
(`326980220+psjg-claude@users.noreply.github.com` for Claude sessions); the GitHub App sets
its own in `claude.yml`. `set` checks only that the value looks like an address: storing the
right one is yours. At commit time `.githooks/commit-msg` wants the author to be the address
stored here, whichever it is. `scripts/commit-lint`, at the push, also accepts the addresses
of `.github/agent-emails`; in CI, where nothing is stored here, it accepts only the list the
workflow sets (`FPL_AGENT_EMAILS`), and there a person's address does not pass as an agent's.
