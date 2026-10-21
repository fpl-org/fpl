---
name: fpl:commit:acommit
description: Assemble and make a commit with scripts/acommit, which writes the header, the body, the provenance trailers and the machine-account author. Use for every commit an agent makes; never a bare git commit.
---

    scripts/acommit -t <type> -s <scope> -m "<summary>" [-b "<paragraph>"]... [-r <ref>]...
                    [-a <advisor>]... [-K <stack>] [-M "<model>"] [-S <session id>] [-n] [-- <git commit args>]

The type is one of `COMMIT_TYPES` in `.githooks/commit-rules`; the scope is a lower-case noun
for the area touched, of the characters `COMMIT_SCOPE_CHARS` allows there (`.agents/COMMITS.md`
names the usual ones); the summary is imperative, lower-case, without a period.
Without `-b`, the body is read from stdin, one paragraph per blank line, lines at most
`COMMIT_BODY_MAX` wide: say why, never what the diff shows. The model is `-M`, else
`FPL_MODEL`, else `CLAUDE_CODE_MODEL`; the session is `-S`, else `FPL_SESSION_ID`, else
`CLAUDE_CODE_SESSION_ID`, never invented. `Stack:` comes from the branch (`-K` overrides),
`-r` adds `Refs:`, `-a` an `Advisor:`, `-B`/`-k` a breaking change, `-H` a human-only
commit without agent trailers. `-n` prints the message and the git command and commits
nothing. Everything after `--` reaches `git commit` (`-- --amend`).

- **Exit 0**: committed, as the hooks accepted it; with `-n`, the message and the command
  printed, nothing committed and no hook run.
- **Exit 1**: git's own: a hook refused, or git had nothing to commit. `.githooks/commit-msg`
  names the rule, the part that fails and the remedy, and prints the command that brings the
  message back into an editor; `atomic-check` (Haiku) saw more than one logical change: split
  the staging. Fix and run again; `FPL_ATOMIC_GATE=warn` only when you can say why in the
  message. Also 1, before git runs: an option given last without its value (`-t` alone),
  which bash reports as an unbound variable.
- **Exit 2**: nothing was committed: a missing or invalid type, scope or summary, a header or
  body line too long, an unknown argument, no identity (`fpl:commit:identity`), no session
  id, or no model name.

Outside the dev shell the pre-commit leak gate has no `gitleaks`: run it as
`nix develop -c scripts/acommit ...`.
