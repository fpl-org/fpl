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

## Land

Merge the bottom PR first; GitHub retargets the next one to `main`. `scripts/restack` after
each merge to drop the landed commit from your local stack. When the stack is empty, delete
the `stack/…` refs.

## Why this and not a feature branch

A feature branch bundles N changes into one review. A stack keeps each change small enough to
review well, lets independent pieces land as soon as they're approved, and keeps `main`
history linear and bisectable. The cost — restacking on churn — is one command here.
