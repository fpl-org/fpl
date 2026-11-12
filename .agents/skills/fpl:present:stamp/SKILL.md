---
name: fpl:present:stamp
description: Write the Presented-By trailer on every commit of a presented series, with scripts/present stamp. Use once the series is built and scripts/series stamp has run, before any check.
---

Once the series is built and `scripts/series stamp <B>..HEAD` has run, before any check:

    scripts/present stamp <B>..HEAD [value]

It writes `Presented-By: <model slug> <session id>` last in the trailer block of every commit
of the range, keeping the author, the tree and every other trailer. The value is the third
argument, else read from `FPL_MODEL` and `FPL_SESSION_ID` as `scripts/acommit` reads them.
Stamping twice changes no hash. Nothing touches a message after the manifest is taken.

- **Exit 0**: stamped. Go on to the checks.
- **Exit 1**: a hook refused an amend, changed its tree or rewrote another line of its
  message. The rebase is undone, HEAD is where it was, and the refusal is printed. A
  presentation changes messages only, so a change the hook wants in the code goes back to the
  builder.
- **Exit 2**: refused before the rebase, on main, on a dirty tree, mid-rebase, on a range that
  does not end at HEAD or whose base is not an ancestor, on an empty range or one with a
  merge or a message not in UTF-8, or where an untracked file stands at a path the range
  writes or removes. Fix what the message names and run it again.

The full presenter brief, from work tip to review card, is `.claude/agents/presenter.md`.
