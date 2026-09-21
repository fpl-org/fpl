# WORKFLOW.md — stacked commits, git-native

FPL uses a **stacked-commits** workflow (the Meta/Phabricator and Google model): a change is a
short chain of small, individually reviewable commits, each depending on the one below. No
extra tooling — plain git, one config flag, and `scripts/restack`. If you prefer `jj`, see
`docs/JJ.md`; it produces the same history.

Vocabulary: **base** (the branch you'll land on, `main`) · **stack** (your ordered commits on
top of base) · **restack** (rebase the stack when base or a lower commit changes) · **land**
(merge the stack into base).

## The rules

1. **One logical change per commit.** `docs/COMMITS.md` governs the message; the
   `atomic-check` hook blocks commits that bundle unrelated concerns.
2. **Stage at hunk level** (`git add -p`) so unrelated edits don't ride along.
3. **Order matters.** Put a change *below* anything that depends on it. If B needs A, commit A
   first.
4. **A reviewable boundary gets a branch ref.** One PR per ref; each PR targets the ref below
   it (or base for the bottom one).
5. **Never rewrite a commit that others have based work on** without telling them — restacking
   rewrites SHAs.
6. **Everything lands through a GitHub pull request** — harness changes included. No local
   merge into `main`, no direct push to it. See [Land](#land--through-github-for-now).
   **[gate]** `.githooks/reference-transaction` lets local `main` move only to the commit
   `github/main` already points at: `git pull` after a landed PR passes; a commit, a merge
   (fast-forward or not) and a rebase on `main` are refused, and `--no-verify` does not skip
   it. `.githooks/pre-commit` adds the early, friendlier refusal for `git commit` alone.
   `FPL_MAIN_GATE=warn` overrides both; the forge-side half is the ruleset on `main`.
   To update `main` without checking it out: `git fetch github && git branch -f main github/main`
   (or `git fetch --atomic github main:main`; without `--atomic` git moves `main` before
   `github/main`, and the gate refuses it).
7. **The repository must stay self-sufficient.** The forge is where review happens, not where
   the record lives: every commit carries its `Stack:` trailer (`docs/COMMITS.md`), and
   anything a review changes about the *why* is folded back into the commit body before
   landing. If GitHub vanished, `git log` alone should still explain every decision.
8. **A change to the CI goes through the maintainer's hands.** A workflow on a branch of this
   repository runs with the repository's secrets before anyone has reviewed it, so whoever
   can push a file under `.github/workflows/` can read them. Agents push over HTTPS with a
   token that has no Workflows permission, and the forge refuses such a push from it. The
   maintainer pushes those branches himself, over SSH, with a key that needs a touch for
   every use (a Secure Enclave key; checked, it asks each time, twice in a row too). No key
   that works without him is registered for the account on a machine where agents run.

## Setup (once per clone/worktree)

```
scripts/setup
```

sets `rebase.updateRefs=true` (carry intermediate branch refs during rebase),
`rerere.enabled=true` (remember conflict resolutions across restacks), and points git at
`.githooks/`.

**Remotes are named after the place they are**, not after their role: `github`, not `origin`.
The repository is meant to live in more than one place (rule 7), and with two remotes
`origin` says nothing about which is which. After a clone:

```
git remote rename origin github
```

The scripts assume no remote name: `scripts/restack` follows the upstream of the base
branch, `scripts/pr` the remote the branch tracks. The recipes below spell `github`.

## Build a stack

```
git switch -c stack/typed-let/tip main     # start the stack off base; you work on …/tip
# … edit …
scripts/acommit -t feat -s parser -m "parse let-bindings"      # commit 1 (bottom)
git branch stack/typed-let/1                # ref at the first reviewable boundary
# … edit …
scripts/acommit -t feat -s eval -m "evaluate let-bindings"     # commit 2
git branch stack/typed-let/2
```

Now open PRs bottom-up: `…/1` → `main`, `…/2` → `…/1`.

Ref names: a stack is `stack/<name>` when it will be a single PR, or `stack/<name>/tip` plus
numbered boundary refs when it will be several. Never both for one `<name>` — git stores refs
as paths, so `stack/typed-let` and `stack/typed-let/1` cannot coexist (`cannot lock ref`).
An agent's stack is the same name under `agent/<id>/`: `agent/claude/stack/typed-let/tip`. The
full grammar, and the gates that enforce it, are in `docs/BRANCHES.md`.

## Restack (base moved, or you amended a lower commit)

```
scripts/restack            # git fetch github && git rebase --update-refs github/main
```

`--update-refs` moves every `stack/typed-let/*` ref that pointed into the stack along with the
rebase, so the PR branches stay correct. Conflicts: resolve, then `scripts/restack --continue`
(or `--abort`). `rerere` replays the same resolution on the next restack.

To amend a commit that isn't on top:

```
git rebase -i --update-refs github/main    # mark the target 'edit', amend, continue
```

## Read the diff with the file around it

```
scripts/review                 the current branch against main
scripts/review -b <base> …     against the branch below, in a stack
scripts/review -s              side by side
```

renders every changed file whole — `git diff -U9999` through `diff2html` — and opens the page
in the browser. A forge shows a hunk and three lines around it; whether a name is already
bound, whether the line above reverses the meaning, whether `set -e` bites here, none of that
is in the hunk, and a reviewer who cannot see it approves what he cannot judge.
`FPL_REVIEW_CONTEXT` changes the number of lines; `-o <file>` writes the page instead of
opening it.

It reads git refs and nothing else: no forge, no network, no account. It works on a branch
that was never pushed, and it survives a change of forge — which is rule 7 applied to the one
part of review that does not need the forge at all.

## Land — through GitHub, for now

```
git push -u github stack/typed-let/1 stack/typed-let/2
gh pr create --base main              --head stack/typed-let/1
gh pr create --base stack/typed-let/1 --head stack/typed-let/2
```

For agent work there are two scripts, one for each side of the review:

```
scripts/pr [-B <base>]     # the agent's side: file the branch as the machine account
scripts/land [<number>]    # the maintainer's side: checks, conversation, diff, then decide
```

`scripts/pr` refuses unless the token it uses belongs to the machine account of
`.git/agent-identity` and the branch on the forge is the commit you have; it does not push.
`scripts/land` waits for the checks, prints the conversation, opens the diff in the browser,
and only after Enter approves, rebase-merges, deletes the branch and updates `main`. The
author of a pull request cannot approve it, which is why the two sides are two accounts.

`scripts/land` needs `gh`, which is not in the default dev shell: `scripts/layer on github`
(`docs/DEVSHELL.md`, "Forge tools are opt-in"), or land in the browser. `scripts/pr` needs
neither: it calls the API with python3 from the default shell.

## A public mirror of a pijul channel

Not in use yet: this repository still lives in git. `scripts/mirror` and `scripts/import-pr`
are ready for the day the code moves to pijul and a public forge becomes a mirror of it
rather than the home of it. Needs the `pijul` layer (`scripts/layer on pijul`).

The shape is three one-way flows, each piece of state with exactly one home:

- **Out.** `scripts/mirror <pijul> <git> [<channel> [<branch>]]` projects a channel onto a
  branch. It is deterministic — authors, dates and trees all come from the changes — so the
  same changes give the same commit ids and exporting again is a no-op. Every commit carries
  `Pijul-Change: <hash>`.
- **In.** A pull request is fetched without any forge API (`git fetch <forge>
  pull/<n>/head:refs/pull/<n>/head`) and `scripts/import-pr` records it as one pijul change
  under the contributor's name, with `Git-Commit:` and `Landed-By:` in its description. The
  record hooks run on it like on anything else.
- **Back.** On the next export the contributor's own commit is put on the branch — reused as
  is when it already has the right parent and tree, otherwise joined by a merge commit in the
  lander's name. A forge that sees a pull request's commits reach its base branch shows it as
  merged, so the contributor sees an ordinary merged PR and keeps their commit in history.

**`main` in pijul only grows.** Landed is frozen. The mirror refuses (exit 3) to export a
`main` that no longer descends from what it exported before, because that would be a force
push on a public branch. Stacks live on other channels and go to other branches, which may be
rewritten — `scripts/mirror -f` — exactly as a pull request branch may be on any forge.

What stays two-sided: the review conversation happens where the contributor is, in the pull
request thread. Summarise it into the change's description when landing so the reasons stay
here. CI on the forge is a courtesy to the contributor; the gate is the pijul record hooks.

`scripts/mirror --self-test` runs both scripts against a real pijul and git: determinism,
append-only exports, a PR on the latest `main` reused as is, a PR on an older `main` merged
in under the lander's name with the contributor's commit kept, and the refusal to rewrite.

## Bring the review home

```
scripts/import-review <number>...   those pull requests, into Radicle patches
scripts/import-review --open        every open one
```

The code already has a home that is not the forge; the conversation about it did not. This
carries a pull request into a Radicle patch in the repository: the head as a revision, based
on the branch below so a stack shows one layer at a time, and every comment, line comment,
reply and verdict as a comment on that revision, at the same lines. After the import the
patch is the record, and it replicates like the rest.

A comment arrives signed by whoever ran the import, since the forge user has no key. Its first
line says who wrote it on the forge, when, and links it: a claim, not a signature. The link is
also how a second run skips it, so importing twice changes nothing. The Radicle review itself
stays empty, because Radicle keeps one review per signer per revision, and that one is for
the verdict of whoever runs the import.

It pushes to the `rad` remote and so needs `rad` (`scripts/layer on radicle`) and the key in
the agent. `--self-test` runs it in a throwaway Radicle home without the network.

```
scripts/review --serve       the open patches, in the browser
```

reads the patches and nothing else, and lays them out like a mailbox: the open patches down
the left, a patch based on another one's head indented under it, and the chosen one on the
right, on its latest revision, with every changed file whole and each comment under the
lines it is about. `j` and `k` move through the list. Only what is in Radicle shows:
`scripts/import-review --open` first, to bring the pull requests in. What you write there goes into the
patch under your key, the way the Radicle CLI writes it: a line comment into your review of
the revision, a reply into the thread it answers, accept or reject as your review's verdict.
Comments in a review can be resolved; imported ones cannot, because Radicle keeps them on
the revision, where there is no resolve, so they are answered instead.

It does not merge and does not reach the forge. The server listens on 127.0.0.1 only and
wants the token in the address it prints, so no other page in the browser can write to it.

## The agent's credential

`.git/agent-credentials`, mode 600, one line:

```
https://<machine account>:<token>@github.com
```

That is git's credential-store format, so the same file serves a push and `scripts/pr`:

```
git -c credential.helper="store --file=$PWD/.git/agent-credentials" push origin <branch>
```

It sits inside `.git/`, so it is per clone and never committed. The token is a fine-grained
personal access token of the machine account, scoped to this repository alone, with Contents
and Pull requests read/write and Metadata read — and no Workflows. Rule 8 is then a property
of the credential rather than of anyone's discipline: the push is refused, not remembered to
be avoided.

The maintainer creates it (the account's settings, then approve the request as an owner of
the organisation) and writes the file. It expires; a push then fails with 403 and a new token
is made the same way. Agents read it through git and never print it.

- Merge the bottom PR first, with **Rebase and merge**, and delete its branch. GitHub then
  retargets the next PR to `main`. Rebase-merge puts every commit on `main` individually,
  message and trailers intact, with no merge commit — history stays linear and bisectable.
- **Never squash a multi-commit PR.** Squashing collapses the atomic commits, and their
  bodies and trailers, into one. (A one-commit PR is the only case where it is harmless.)
- GitHub's rebase-merge always rewrites the SHAs and the committer. So `scripts/restack` after
  each merge: the rebase recognises the landed commits as already applied and drops them from
  your local stack.
- When the stack is empty, delete the `stack/…` refs, locally and on `github`. Nothing is lost:
  the grouping lives in each commit's `Stack:` trailer, the discussion in the PRs.

```
git log --grep='^Stack: typed-let$'       # the whole stack, years later, forge or no forge
```

"For now" is deliberate. PRs are the review surface because they are the one at hand, not
because the record belongs on a forge; rule 7 keeps the switch to an in-repo review system
cheap.

## Why this and not a feature branch

A feature branch bundles N changes into one review. A stack keeps each change small enough to
review well, lets independent pieces land as soon as they're approved, and keeps `main`
history linear and bisectable. The cost — restacking on churn — is one command here.
