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
   `origin/main` already points at: `git pull` after a landed PR passes; a commit, a merge
   (fast-forward or not) and a rebase on `main` are refused, and `--no-verify` does not skip
   it. `.githooks/pre-commit` adds the early, friendlier refusal for `git commit` alone.
   `FPL_MAIN_GATE=warn` overrides both; the forge-side half is the ruleset on `main`.
   To update `main` without checking it out: `git fetch origin && git branch -f main origin/main`
   (or `git fetch --atomic origin main:main`; without `--atomic` git moves `main` before
   `origin/main`, and the gate refuses it).
7. **The repository must stay self-sufficient.** The forge is where review happens, not where
   the record lives: every commit carries its `Stack:` trailer (`docs/COMMITS.md`), and
   anything a review changes about the *why* is folded back into the commit body before
   landing. If GitHub vanished, `git log` alone should still explain every decision.
8. **A change to the CI goes through the maintainer's hands.** A workflow on a branch of this
   repository runs with the repository's secrets before anyone has reviewed it, so whoever
   can push a file under `.github/workflows/` can read them. Agents push over HTTPS with a
   token that lacks GitHub's `workflow` scope, and the forge refuses such a push from it. The
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
scripts/restack            # git fetch origin && git rebase --update-refs origin/main
```

`--update-refs` moves every `stack/typed-let/*` ref that pointed into the stack along with the
rebase, so the PR branches stay correct. Conflicts: resolve, then `scripts/restack --continue`
(or `--abort`). `rerere` replays the same resolution on the next restack.

To amend a commit that isn't on top:

```
git rebase -i --update-refs origin/main    # mark the target 'edit', amend, continue
```

## Land — through GitHub, for now

```
git push -u origin stack/typed-let/1 stack/typed-let/2
gh pr create --base main              --head stack/typed-let/1
gh pr create --base stack/typed-let/1 --head stack/typed-let/2
```

`gh` is not in the default dev shell. Get it with `nix develop .#github` (`docs/DEVSHELL.md`,
"Forge tools are opt-in"), or file the PRs in the browser.

- Merge the bottom PR first, with **Rebase and merge**, and delete its branch. GitHub then
  retargets the next PR to `main`. Rebase-merge puts every commit on `main` individually,
  message and trailers intact, with no merge commit — history stays linear and bisectable.
- **Never squash a multi-commit PR.** Squashing collapses the atomic commits, and their
  bodies and trailers, into one. (A one-commit PR is the only case where it is harmless.)
- GitHub's rebase-merge always rewrites the SHAs and the committer. So `scripts/restack` after
  each merge: the rebase recognises the landed commits as already applied and drops them from
  your local stack.
- When the stack is empty, delete the `stack/…` refs, locally and on `origin`. Nothing is lost:
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
