---
name: fpl:series:manifest
description: Compute what identifies a range of commits beyond their SHAs, with series manifest, digest and check. Use when a presented series needs its receipt for the review card, when two ranges must be shown to be the same review, and to prove a range carries one Series-Id.
---

    .agents/skills/fpl:series/scripts/series manifest <range>   JSON, one entry per commit
    .agents/skills/fpl:series/scripts/series digest <range>     the digest alone, 64 hex digits
    .agents/skills/fpl:series/scripts/series check <range>      exactly one Series-Id; prints it

The manifest lists, per commit, the sha, the patch id (`git patch-id --verbatim` of its diff,
pinned against the caller's diff configuration; `--stable` gave one id to a file and its
re-indented copy) and the SHA-256 of author and raw message, plus one digest over all (patch
id, message) pairs. The SHAs are listed but left out of the digest, so equal digests mean the
same patches, in the same order, with the same authors and messages. It is byte-stable: no
clock, no config of the caller's in the diff.

The digest is the receipt: the review card carries it (`.agents/REVIEW-CARD.md`), and the
lander writes it as the `fpl/series` check run on the head it lands, computed with `main`'s
copy of the script. Take the manifest last, after every stamp.

- **Exit 0**: the output named above, and nothing else on stdout.
- **Exit 1**: `range` (an empty range, or one git cannot read), `series-missing` (a commit
  without the trailer), `series-many` (a commit with two), `series-mixed` (two ids in the
  range), each with a remedy; `digest` then prints nothing on stdout.
