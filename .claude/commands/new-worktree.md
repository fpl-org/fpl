---
description: Create a new implementation worktree under worktrees/<name>/
argument-hint: <name> [base-branch]
---

Load the skill `fpl:worktree:new` and follow it with `-a claude`, name `$1`, base `$2` (default
`main`); report the path and branch, then stop.
