---
name: fpl:pr:whoami
description: Which account a push from this checkout would go out as, with .agents/skills/fpl:pr:whoami/scripts/whoami-check. Use before any push from an agent worktree, and when a pull request or commit turned up under the maintainer's own account.
---

    .agents/skills/fpl:pr:whoami/scripts/whoami-check [<destination url>]

Three identities can write to GitHub from one machine: git's credential helper (`username=`),
the active `gh` account, and the ssh key. It prints each, and a `NAG` line when one is an
admin account (`FPL_ADMIN_ACCOUNTS`, default `psjg`): a push would then go out as the
maintainer, and nobody could approve it. Given the URL a push goes to, it judges only the
identity that transport uses; `.githooks/pre-push` runs it so, first, as a message.

- **Exit 0**, always: a message, never a gate. Read the lines; with a `NAG`, push by the
  remedy it prints, the machine account's token in the URL:
  `TOKEN=$(gh auth token --user psjg-claude); git -c credential.helper= push "https://x-access-token:$TOKEN@github.com/fpl-org/fpl.git" HEAD:refs/heads/<branch>`.
  Never print the token; the script never reads a password into a variable.

Each probe is cut off after `FPL_WHOAMI_DEADLINE` seconds (10), so a key waiting on a touch
or a helper opening a dialog cannot hold a push.
