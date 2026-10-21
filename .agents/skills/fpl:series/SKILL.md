---
name: fpl:series
description: Give a series of commits the identity that outlives every rewrite, and prove it, with the series script in this skill's scripts/ (mint, stamp, check, manifest, digest, range, revert). Use when a branch is about to be pushed for review, presented, relocated or reverted; it runs the sub-skills stamp and manifest, and holds restack, range and revert.
---

A branch name and a SHA change when a series is rebased, reordered or moved; the `Series-Id:`
trailer (`.agents/COMMITS.md`) does not. It is minted once, `<topic>-<7 hex of the tip it was
minted at>`, and carried by every commit. There is no patch-id trailer: a stored one goes stale
on a move; the manifest computes it on demand. The script, from the repository root:

    .agents/skills/fpl:series/scripts/series <cmd> ...      mint | stamp | check | manifest
                                                            | digest | range | revert

The routine, on a work branch whose base is `<B>` (`github/main`, or the parent of a sub-series):

1. **Mint**: `series mint <branch>` prints the id for this branch at this tip. `stamp` mints
   one itself when the range carries none, so this step is only for reading the id early.
2. **Stamp**: load `fpl:series:stamp`; `series stamp <B>..HEAD` puts one id on every commit.
3. **Manifest**: load `fpl:series:manifest`; `series manifest <B>..HEAD` is what a reviewer
   and the lander compare, `digest` its one-line receipt, `check` the proof of one id.

Moving the series on a moved base is `fpl:series:restack`; finding a landed series on `main`
is `fpl:series:range`, undoing it whole is `fpl:series:revert`.

- **Exit 0**: done; `mint`, `check` and `digest` print one line, `manifest` JSON.
- **Exit 1**: refused, as `series [<rule>]: <what>` with a remedy line, nothing on stdout:
  `usage`, `range`, `base`, `branch`, `checked-out`, `series-*`, `owner-spoke`, `forge-*`,
  `main-ref`, `rebase`, `range-*`, `revert-*`, `dirty`; each sub-skill names its own.

`SERIES_MAIN` names main (default `github/main`, then `origin/main`, then `main`; once set it
must resolve), `SERIES_GH`, `SERIES_REPO` and `SERIES_OWNER` the forge, read only, with the
machine account's token. Plain bash 3.2. `series-self-test` beside it proves every rule.
