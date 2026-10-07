# COMMITS.md — commit message & authorship convention

Every commit MUST follow this. The header is
[Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/); the trailer
block is a [git trailer](https://git-scm.com/docs/git-interpret-trailers) list. Together they
give a log that `git log --format`, `git interpret-trailers --parse`, and a changelog
generator can all read, while staying legible for a human doing archaeology years later.

`scripts/acommit` assembles a compliant message; `.githooks/commit-msg` validates every
commit independently. Each rule below is marked **[gate]** (a hook rejects violations) or
**[advisory]** (documented, not machine-checkable — a hook cannot reliably tell).

The hook only sees a commit made with git, in a clone whose hooks are wired.
`git commit --no-verify`, an unwired clone and `jj` (`docs/JJ.md`) get past it. So the same
gates run a second time where they cannot be skipped: `scripts/commit-lint <rev-range>` runs
the hook over commits that already exist, and `.github/workflows/commit-lint.yml` does that
for every commit of a pull request. `.githooks/pre-push` runs it too, over the commits a push
adds to a branch, judged for the branch they arrive at: a commit moved since it was made
(cherry-pick, `rebase --onto`, `branch -f`) still carries the `Stack:` of the branch it left,
and is refused before it reaches the forge. By hand, for a branch based on `main`:

```
scripts/commit-lint -b "$(git branch --show-current)" github/main..HEAD
```

For a branch based on a parent not merged yet, the base is that parent on the remote, so
the parent's commits, which may carry another `Stack:`, are left out as the hook leaves
them out. Set `PARENT` to the parent branch's name first:

```
PARENT=agent/claude/stack/parent-name
scripts/commit-lint -b "$(git branch --show-current)" "github/$PARENT..HEAD"
```

The agent addresses it accepts beside `.git/agent-identity` come from one of two lists. In
CI the workflow sets `FPL_AGENT_EMAILS` inline, and that list is the only one trusted: the
checkout is the pull request's own tree, so a pull request could otherwise add its author to
a file and pass. The file `.github/agent-emails` serves the local hooks (`commit-msg`,
`pre-push`), which run with the variable unset, and must be a subset of the workflow's list;
`scripts/commit-lint` refuses, naming the address, when the file lists one the variable
lacks. Add an address to the workflow first (an agent's token cannot push
`.github/workflows/`, so the owner does), then to the file.

Judged after the fact, a `fixup!`, `squash!` or `amend!` commit fails (a rebase-merge would
land it as it is), and the atomicity check is skipped. When it is made, such a commit is
spared every gate but the path guards: one that edits a protected spec or policy file carries
its own marker (`git commit --fixup=<commit> -m "[spec]"`).

A real merge and a real revert pass unjudged, since git wrote their messages. A merge is a
`Merge ...` commit with more than one parent (or one in the making); a revert is a commit,
under any title, whose line `This reverts commit <id>` names a commit that exists, in either
form git writes (`<sha>.` under its `Revert "..."` or `Reapply "..."` title, or
`<abbrev> (<subject>, <date>).` from `git revert --reference` or `revert.reference=true`;
`, reversing` for the revert of a merge, `git revert -m N`), the id naming one commit, over
the tree `git revert` makes of that commit (the same merge, by `git merge-tree`: the reverted
lines come back where they were, and a file renamed since is followed). Any other
commit that opens with those words is judged like every commit, and so is a revert whose
conflicts were resolved by hand. git does not tell `commit-msg` that a commit is an amend, so
an amend of a merge or revert is refused there, reworded or not: amend one with
`git commit --amend --no-verify` (commit-lint skips merges).

## Message format

```
<type>(<scope>)<!?>: <summary>
                                  <- exactly one blank line
<body>
                                  <- exactly one blank line
<trailer block>
```

### Header — one line

- **[gate] ≤ 72 characters**, whole line.
- **[gate] type** ∈ `feat` `fix` `docs` `refactor` `perf` `test` `build` `ci` `chore` `revert`.
- **[gate] scope** — present, in parens, `[a-z0-9/._-]+`. A noun for the touched area. Harness
  scopes: `harness` `docs` `stack` `conventions` `commits` `workflow` `worktree` `hooks`
  `commands` `agents` `skill` `scripts`. Worktree scopes: `grammar` `parser` `desugar` `core`
  `eval` `types` `errors` `driver` `repl`, or a `features/<name>` name.
- **[gate] `!`** before the `:` iff breaking; also add a `BREAKING-CHANGE:` trailer.
- **[gate] summary** follows `: ` directly, starts lower-case, no trailing period.
- **[advisory] summary** in the imperative ("add", not "adds"/"added").

### Body — required unless the change is trivially self-evident

- **[gate]** exactly one blank line between header and body.
- **[gate]** lines ≤ 72 columns. Exceptions the hook allows: fenced code blocks, table rows
  (`| … |`), and a line with no break opportunity past column 72 (a long URL or path).
- **[advisory]** content is *why*: the problem, motivation, constraints, alternatives
  rejected — never a narration of the diff. Reference decisions by file (`docs/STACK.md`).

### Trailer block

- **[gate]** one blank line before it; each line `Token: value`, tokens use `-` for spaces.
- **[gate]** `Assisted-By` **and** `Session-Id` are both present — **or** a single
  `Human-Only: true` line for a hand-made human commit.
- **[gate]** on a stack branch — `stack/<name>[/<part>]`, or the same under `agent/<id>/`
  (`docs/BRANCHES.md`) — the message carries `Stack: <name>`; the value is always `[a-z0-9][a-z0-9._-]*`. `scripts/acommit` derives it
  from the branch (`-K <name>` overrides). Stack refs are deleted after landing and a linear
  landing leaves no merge commit, so this trailer is the in-repo record of which commits formed
  one unit: `git log --grep='^Stack: typed-let$'` recovers the stack years later, forge or no
  forge.
- `scripts/acommit` takes the session id from `-S <id>`, else `$FPL_SESSION_ID`, else
  `$CLAUDE_CODE_SESSION_ID`, and refuses to commit when none is set — any harness can
  export `FPL_SESSION_ID`. It never invents one: a made-up id is useless for forensics.
- **[gate]** known trailers appear in this order:

  | Trailer | Meaning | Example |
  | --- | --- | --- |
  | `Refs` | path / issue / feature this commit serves (repeatable) | `Refs: docs/STACK.md` |
  | `Stack` | the stack this commit landed as part of (`docs/WORKFLOW.md`) | `Stack: typed-let` |
  | `BREAKING-CHANGE` | required iff `!` in header | `BREAKING-CHANGE: core drops Let node` |
  | `Advisor` | an external model whose output informed the change (repeatable) | `Advisor: fable-5.1` |
  | `Assisted-By` | the model that produced the change, stable slug | `Assisted-By: claude-sonnet-5` |
  | `Reasoning-Effort` | that model's reasoning-effort setting | `Reasoning-Effort: low` |
  | `Session-Id` | the agent session id, for forensics | `Session-Id: d94ffb13-…` |
  | `Co-Authored-By` | co-author, GitHub-parseable form (repeatable) | `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` |

## Atomicity

- **[gate, soft]** `.githooks/atomic-check` sends the staged diff + message to a cheap model
  (Haiku) and blocks a commit the model judges to bundle unrelated concerns. It is a *soft*
  verifier — weaker than the symbolic gates — so it **fails open**: any infrastructure problem
  (no model reachable, unparseable reply) skips the check rather than blocking.
  - `FPL_ATOMIC_GATE=block` (default) · `warn` (print, don't block) · `off` (skip).
  - `FPL_ATOMIC_STRICT=1` also blocks when the model could not be reached.
  - Verdicts are cached under `.git/atomic-cache/` keyed on tree+message, so `--amend` loops
    don't re-bill. Cost is one Haiku call (~seconds) per distinct staged state.
- **[advisory]** one logical change per commit; stage at **hunk** level (`git add -p`) so a
  commit never bundles unrelated edits. New files are one hunk by nature.

## Authorship

Two identities, deliberately kept apart.

### 1. Local (terminal-session) commits — a GitHub machine account

- **[gate] author** = `<model display name> <machine-account email>`, e.g.
  `Claude Sonnet 5 <NNNNN+psjg-claude@users.noreply.github.com>`.
  - The **name carries the model** (`Claude Sonnet 5`, `Claude Opus 5`, `Claude Haiku 4.5`, …)
    so `git shortlog -sn` shows at a glance who committed what.
  - The **email is one constant address** — the GitHub noreply of a dedicated machine account
    (a normal GitHub login made for automation, *not* a Unix account) — so every model still
    links to a single contributor on the forge.
  - `.githooks/commit-msg` rejects a non-`Human-Only` commit whose author email is not the one
    in `.git/agent-identity`.
- **committer** stays whoever ran the session (their normal `git config user.*`).
- **[gate] agent territory** — a commit that is not `Human-Only` sits on an agent branch:
  `agent/<id>/…`, or the flat vendor form `<id>/<slug>` (`docs/BRANCHES.md`). The branch's
  `<id>` names its lead, not an exclusive author, so it is not compared with `Assisted-By`:
  a Codex commit on a Claude-led branch is legal and attributed by its own author name and
  trailers. Human commits on agent branches are legal too. `FPL_BRANCH_GATE=warn` overrides.
- Set up once per clone/worktree:

  ```
  scripts/agent-identity set "NNNNN+psjg-claude@users.noreply.github.com"
  ```

  This writes `.git/agent-identity` (inside `.git/`, per-worktree, never committed).
  `scripts/acommit` reads it and refuses to commit if it is unset.

### 2. Forge-originated work — the Claude GitHub App

CI runs and `@claude` interactions on issues/PRs are authored by the **`claude[bot]`** account
(the [Claude GitHub App](https://github.com/apps/claude), installed on this repo). Different
email, independent identity — no collision, no impersonation either way.

`.github/workflows/claude.yml` wires the hooks in the App's runner before it starts
(`scripts/setup`, and `scripts/agent-identity set` with the bot's own address), so a commit
it makes there meets the same `commit-msg` as one made in a terminal. It commits with
`scripts/acommit`: the author name carries its model, `Session-Id` is `gha-<run id>` and
leads back to the Actions run. `scripts/commit-lint` holds its commits to every gate; the
App's address is one of the accepted agent addresses (the workflow's list, mirrored in
`.github/agent-emails`).

GitHub links a commit to an account by matching the author/co-author **email** to one
registered on that account. `noreply@anthropic.com` is not a forge account, so a bare
`Co-Authored-By: Claude …` line is provenance only, never a contributor-graph entry — hence
the machine account.

## Example

```
docs(stack): record settled implementation stack decision

The stack was chosen with the maintainer after consulting two external
advisors and must survive across worktrees and sessions without being
reopened each time. Recording the decision and its rejected alternatives
makes "why Python and not OCaml" answerable from the log alone.

Refs: docs/STACK.md
Advisor: fable-5.1
Advisor: chatgpt
Assisted-By: claude-sonnet-5
Reasoning-Effort: low
Session-Id: d94ffb13-ae66-411c-acd2-34b23e151b71
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
```

See `docs/WORKFLOW.md` for how commits stack and restack.
