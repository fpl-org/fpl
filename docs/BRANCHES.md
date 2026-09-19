# BRANCHES.md — the branch-name grammar

Every branch name in this repository parses. A name says who is working (a human, or which
agent), what kind of work it is, which stack it belongs to, and where in the stack it sits —
without consulting the forge. `scripts/branch-lint` is the grammar as an executable and the
only parser; every gate below calls it, so this document and the gates cannot drift apart
silently (`scripts/branch-lint --self-test`).

## Grammar

```abnf
branch  = "main" / work / agent / vendor / legacy

work    = "stack/" name [ "/" part ]     ; a stack: one PR, or tip + boundary refs
        / "attempt/" name                ; an implementation worktree (WORKTREES.md)

agent   = "agent/" id "/" work           ; agent work, full hierarchy
vendor  = id "/" slug                    ; escape hatch, flat, tool-imposed

id      = "claude" / "codex" / "copilot" / "cursor" / "jules" / "ai"
name    = lower *( lower / "." / "_" / "-" )
part    = "tip" / 1*DIGIT [ "-" name ]   ; order, optional label: 1, 03-api
slug    = 1*( ALPHA / DIGIT / "." / "_" / "-" )
lower   = %x61-7A / DIGIT
legacy  = "fpl_a"                        ; predates the grammar
```

All of it sits on top of git's own rules (`git check-ref-format`): git allows `/` to any depth,
but a ref cannot be both a leaf and a directory, so a stack is either `stack/<name>` (a single
PR) or `stack/<name>/tip` plus numbered boundary refs — never both for one `<name>`.

| Example | Reads as |
| --- | --- |
| `stack/typed-let` | human stack `typed-let`, single PR |
| `stack/typed-let/tip`, `…/1`, `…/02-eval` | human stack, working tip and two review boundaries |
| `agent/claude/stack/typed-let/tip` | the same, worked by Claude |
| `agent/codex/attempt/b` | implementation attempt `b`, worked by Codex |
| `claude/issue-12-20260919-1234` | vendor form: a Claude tool that could not be told otherwise |

## Agents: hierarchy by default, a flat escape hatch

An agent that can choose its branch name **must** use the `agent/<id>/…` form. One glob,
`agent/**`, then covers every agent on the forge, and the rest of the name keeps the same
fields a human branch has, so `Stack:` trailers, restacking and review boundaries work
unchanged.

Some tools hard-code their namespace and only emit `<tool>/<flat-slug>`: GitHub's Copilot
agent can push only to `copilot/…`, Claude Code's cloud sessions treat `claude/…` as the
pre-approved prefix, and `claude-code-action` defaults to `claude/`. The grammar does not fight
them: `vendor` admits exactly that shape — a known id, one slash, a free-form slug. It is
deliberately flat. `claude/stack/x/tip` is rejected with a pointer to `agent/claude/…`, so the
escape hatch cannot become a second, parallel hierarchy.

The ids reuse the agent prefixes registered by
[Conventional Branch](https://conventionalbranch.org/) v1.1.0 (plus `jules`). That spec is
otherwise too flat to adopt — its grammar is `type "/" description` with no `/` allowed in the
description — but sharing its vocabulary keeps vendor-form branches valid under both.

## Several agents on one branch

`<id>` names the branch's **lead** — the agent that opened it and drives it — not an exclusive
author. A stack is routinely worked by more than one party: Claude writes, Codex reviews and
pushes a fix, the maintainer amends a message. Forcing each of them onto a branch of their own
would turn one stack into three and defeat the point of stacking.

So the two questions are answered in two places. *Whose territory is this branch?* is in the
ref: `agent/claude/…`. *Who made this change?* is in the commit, where it already lived: the
author name carries the model and `Assisted-By` carries its slug (`docs/COMMITS.md`). A Codex
commit on `agent/claude/stack/typed-let/tip` is legal and fully attributed. When no single
agent leads — a branch opened for several agents from the start — use the id `ai`.

## Why the path does not encode stack topology

A tempting reading of git's `/` is `branch(-of-branch)*`: put a child stack *under* its parent,
to any depth, so the name shows the shape of the stack. Git allows the depth, but the idea
fails, first mechanically and then by design.

Mechanically: a ref cannot be both a leaf and a directory. Next to `stack/x`, git refuses
`stack/x/y` (`cannot lock ref … 'refs/heads/stack/x' exists`), and in a stack parent and child
always exist at the same time, each being the head of its own PR. A leaf suffix works around
it — `stack/x/tip`, `stack/x/y/tip`, `stack/x/y/z/tip` coexist, which is also why ghstack names
its refs `…/head` — but that only makes the following problems reachable:

- **Landing.** Once `x` is merged, `y` hangs off `main`, yet it is still called
  `stack/x/y/tip`. The name now states a parent that no longer exists.
- **Reordering.** Inserting a branch in the middle, splitting one, or re-parenting one means
  renaming every descendant.
- **Renaming costs PRs.** GitHub: "If the renamed branch is the head branch of an open pull
  request, this pull request is closed." One reorder closes the PRs of the whole subtree, and
  their review history with them.
- **Several agents.** A child that Codex writes on a Claude-led stack lives under
  `agent/codex/…`, not under `agent/claude/stack/x/…`. The path hierarchy breaks exactly where
  multi-agent stacks begin.

So the rule is: **the name is identity, the graph is structure.** A name says which stack a
branch belongs to and who leads it — facts that survive landing and reordering. The shape of
the stack is already recorded, exactly once, in the commit graph (and mirrored in each PR's
base), so it is derived, never declared: a branch's parent is the nearest ancestor commit
that carries a stack ref, `main` otherwise. A tree-shaped stack simply gives its parts unique
names under one `<name>`.

The numbered `part` has the same weakness in a milder form: after a reorder `2` may sit below
`1`. Treat the number as a review-order hint; the graph is the authority.

## Gates

| Gate | Where | What it stops |
| --- | --- | --- |
| **[gate]** `reference-transaction` | local, `.githooks/` | *creating* a branch whose name does not parse (`git switch -c`, `git branch`, `git worktree add -b`, a fetch into `refs/heads/`). Git has no branch-creation hook; this is the hook that sees every ref update, and it cannot be skipped with `--no-verify`. Known gap: `git branch -m` (git 2.34 routes only the old name's deletion through the hook); the next two gates catch a renamed branch. |
| **[gate]** `pre-push` | local, `.githooks/` | *pushing* to a remote branch whose name does not parse |
| **[gate]** `commit-msg` | local, `.githooks/` | an agent commit (no `Human-Only: true`) on a branch outside the agent namespaces (`agent/<id>/…`, `<id>/…`). It does **not** compare the commit's model with the branch's `<id>` — see below. Human commits on agent branches stay legal; review fixups are normal. |
| **[gate]** `branch-lint` workflow | forge, `.github/workflows/` | a pull request whose head branch does not parse; make it a required status check to harden it |

`FPL_BRANCH_GATE=block` (default) · `warn` · `off` applies to the three local gates. Existing
branches are never re-judged: the local gates fire on creation, push and commit, not on
checkout, so a branch that predates a grammar change keeps working until it is pushed again.

## Changing the grammar

Edit `scripts/branch-lint` (the patterns, the header comment, and the self-test table) and the
ABNF above in the same commit. A new agent is one more alternative in `id`; a new kind of work
is one more alternative in `work`. Tool-imposed hierarchies that are not agent namespaces (a
stacking tool's `gh/<user>/<n>/head`, say) are deliberately not admitted until the tool is
actually adopted.
