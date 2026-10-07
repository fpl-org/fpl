# WORKFLOW.md — stacked commits, git-native

FPL uses a **stacked-commits** workflow (the Meta/Phabricator and Google model): a change is a
short chain of small, individually reviewable commits, each depending on the one below. No
extra tooling — plain git, one config flag, and `scripts/restack`. If you prefer `jj`, see
`.agents/JJ.md`; it produces the same history.

Vocabulary: **base** (the branch you'll land on, `main`) · **stack** (your ordered commits on
top of base) · **restack** (rebase the stack when base or a lower commit changes) · **land**
(merge the stack into base).

## The rules

1. **One logical change per commit.** `.agents/COMMITS.md` governs the message; the
   `atomic-check` hook blocks commits that bundle unrelated concerns.
2. **Stage at hunk level** (`git add -p`) so unrelated edits don't ride along.
3. **Order matters.** Put a change *below* anything that depends on it. If B needs A, commit A
   first.
4. **A reviewable boundary gets a branch ref.** One PR per ref; each PR targets the ref below
   it (or base for the bottom one).
5. **Never rewrite a commit that others have based work on** without telling them — restacking
   rewrites SHAs.
6. **Everything lands through a GitHub pull request** — harness changes included. No local
   merge into `main`, and no push to it but the one `scripts/land` makes: the fast-forward
   to the head of an approved pull request. See [Land](#land--through-github-for-now).
   **[gate]** `.githooks/reference-transaction` lets local `main` move only to the commit
   `github/main` already points at: `git pull` after a landed PR passes; a commit, a merge
   (fast-forward or not) and a rebase on `main` are refused, and `--no-verify` does not skip
   it. `.githooks/pre-commit` adds the early, friendlier refusal for `git commit` alone.
   `FPL_MAIN_GATE=warn` overrides both; the forge-side half is the ruleset on `main`.
   To update `main` without checking it out: `git fetch github && git branch -f main github/main`
   (or `git fetch --atomic github main:main`; without `--atomic` git moves `main` before
   `github/main`, and the gate refuses it).
7. **The repository must stay self-sufficient.** The forge is where review happens, not where
   the record lives: every commit carries its `Stack:` trailer (`.agents/COMMITS.md`), and
   anything a review changes about the *why* is folded back into the commit body before
   landing. If GitHub vanished, `git log` alone should still explain every decision.
8. **A change to the CI goes through the maintainer's hands.** A workflow on a branch of this
   repository runs with the repository's secrets before anyone has reviewed it, so whoever
   can push a file under `.github/workflows/` can read them. Agents push over HTTPS with a
   token that has no Workflows permission, and the forge refuses such a push from it. The
   maintainer pushes those branches himself, over SSH, with a key that needs a touch for
   every use (a Secure Enclave key; checked, it asks each time, twice in a row too). No key
   that works without him is registered for the account on a machine where agents run.
9. **Nothing private reaches the repository.** It is public, and so is whatever a commit,
   a push or a pull request carries. **[gate]** `scripts/leak-check` runs
   [gitleaks](https://github.com/gitleaks/gitleaks) over the staged change
   (`.githooks/pre-commit`), the message (`.githooks/commit-msg`), every commit and ref
   name a push sends (`.githooks/pre-push`), and a pull request's title and body
   (`scripts/pr`). It judges added lines, file names and messages against two sets of
   rules: gitleaks's defaults, which find keys and tokens, and a private list of terms.
   The list is local and per maintainer, never committed: one regular expression per line
   in Go's RE2 syntax (`\b`, not `\<`), matched regardless of case, `^` and `$` at line
   ends, in `.git/leak-patterns` (this clone and its worktrees) and
   `~/.config/fpl/leak-patterns` (every clone). A space in a line matches any run of
   whitespace, a line break included, so a 72-column wrap cannot split a term. A push
   judges the commits the remote it goes to lacks; a first push to a remote, or to a URL,
   judges the branch's whole history. Its report names the rule, the list line and the
   place, never the match. With no list only the defaults run.
   `FPL_LEAK_GATE=block` (default) · `warn` (report, don't block) · `off`. It covers what
   leaves through git and `scripts/pr`; the comments `scripts/export-review` posts, and
   anything written on the forge by hand, do not pass it.
10. **An approved pull request is frozen; fix forward.** Until the maintainer approves a pull
    request, agents rewrite it freely, in this order: the machines first (`make check` and
    the other lanes of `.agents/QUALITY.md`), then the review bots (CodeRabbit reviews each
    push; Codex review is asked for in that round, not after him), then the fixes, and only
    then his review. From his approval on, nothing is pushed to its branch: no amend, no fix
    commit, no restack, no force push, no deletion. A finding that arrives later is fixed
    forward, in a new pull request on top of the stack that names the finding and the pull
    request it fixes. An approved branch gets no more pushes, so CodeRabbit, which reviews
    each push, does not come back to it; a bot's late finding is work for that new pull
    request, not a reason to reopen the approved one. So he reads each change once, and an
    approval never goes stale. The one exception is a rebase that a real conflict with the
    base or `main` forces: declare it with `FPL_FORWARD_ONLY_OVERRIDE="conflict: <reason>"`
    and repeat the reason in the pull request, because his approval no longer covers what is
    pushed. The forge backs this up only in part. Dismiss-stale-reviews, the tripwire that
    turns a push after an approval into a dismissed approval, is on only for pull requests
    based on `main` and on the branches the review ruleset names (today `walker/01-syntax`,
    `walker/06-match` and `asm-layers`); on any other base the approval stays, on an older
    commit. **[gate]** `.githooks/pre-push` runs `scripts/forward-only`: a push to GitHub
    that would overwrite or delete the branch of an open pull request that a human approved
    is refused, whichever commit he approved, so the gate does not lean on the tripwire. He
    lifts the freeze by dismissing his approval or by requesting changes. Bots, `psjg-codex`
    and `psjg-claude` are not counted as human. It reads the forge with GET requests only,
    with python3 and no `gh`, so it runs in the default dev shell, and refuses when it cannot
    read it; then it says so, and `FPL_FORWARD_ONLY_OVERRIDE="unchecked: <reason>"` lets a
    branch go that you know nobody approved. `git push --no-verify` and `jj git push`
    (`.agents/JJ.md`) skip it, and `git push --mirror` deletes a branch this clone lacks
    without handing pre-push a line for it; that leaves only the tripwire, where it is on.

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
full grammar, and the gates that enforce it, are in `.agents/BRANCHES.md`.

## Restack (base moved, or you amended a lower commit)

Only where nothing is approved yet (rule 10). A restack rewrites every branch of the stack
above the commit it changes, so a change under an approved pull request would rebase that
one too: fix it forward instead. Above the highest approved pull request the stack is still
yours to rewrite, with that branch as the base. A frozen stack does not follow `main`
around; only a real conflict with `main` asks for a rebase, and that is rule 10's declared
exception.

```
scripts/restack            # git fetch github && git rebase --update-refs github/main
```

`--update-refs` moves every `stack/typed-let/*` ref that pointed into the stack along with the
rebase, so the PR branches stay correct. Conflicts: resolve, then `scripts/restack --continue`
(or `--abort`). `rerere` replays the same resolution on the next restack.

To amend a commit that isn't on top, before it is approved:

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
scripts/pr [<branch>]          # the agent's side: file the branch as the machine account,
                               # on the tail of the queue
scripts/land [<number>]        # the maintainer's side: check, look, decide, fast-forward main
scripts/land --dry-run <number>  # every check and the push it would make; changes nothing
```

`scripts/pr` refuses unless the token it uses belongs to the machine account of
`.git/agent-identity` and the branch on the forge is the commit you have; it does not push.
It files the pull request on the tail of the queue, and refuses a branch that is not built
on that tail, with the rebase that puts it there; `-B <base>` overrides the choice.

`scripts/land` lands by **fast-forward**: it pushes the pull request's head to `main`
without force, `git push github <head>:refs/heads/main`. The commits on `main` are the
commits that were reviewed, SHAs, committer and all, and GitHub shows the pull request as
merged once its head is on its base. Before it asks anything it refuses, naming the rule
and the remedy, unless the pull request is open, not a draft and based on `main`; the head
the forge reports is the commit it fetched; the active gh account did not write it; a code
owner's standing verdict approves that exact head (or you are the code owner, and it
approves the head for you after the keypress); nobody's standing verdict requests changes;
every review thread is resolved; every check the rulesets on `main` require concluded
success on the head, judged by its latest run; `main` is an ancestor of the head, and no
merge commit lies between them; every rule on `main` is one it judges; and you may push past
the rulesets on `main`. Then it prints the conversation, opens the diff in
the browser and waits for Enter; after it, it checks everything again, pushes, checks that
`main` is the head and that GitHub shows the merge, and prints the command that retargets
to `main` each pull request based on the landed branch. The author of a pull request cannot
approve it, which is why the two sides are two accounts.

**The merge button is not used for our pull requests**, nor `gh pr merge`. GitHub's merge
methods all write new commits: rebase-merge gives every commit a new SHA and committer, so
each pull request stacked on the landed one has to be rebased and pushed again, its approval
is dismissed, and rule 10 needs an override for the push (fpl-org/fpl#129, #132 and #133
went through that). A fast-forward moves nothing that was reviewed. Squash and merge commits are refused anyway:
`main` is linear and keeps the atomic commits with their trailers.

**The owner's one-time step.** A push to `main` is refused by the rulesets on it unless the
pusher may bypass them always: in Settings > Rules > Rulesets, in each ruleset on `main`,
Bypass list > Repository admin > **Always**, not "For pull requests only".
`scripts/land --dry-run` says, as `land/bypass`, whether that is done; a push the forge
refuses for it gets the same remedy. With it an admin's push skips the rulesets entirely,
force included, so the checks the rulesets made are the ones `scripts/land` makes before it
pushes, and it never forces. Pushing `main` by hand stays what rule 6 forbids.

`scripts/land` needs `gh`, which is not in the default dev shell: `scripts/layer on github`
(`.agents/DEVSHELL.md`, "Forge tools are opt-in"). `scripts/pr` needs neither: it calls the API
with python3 from the default shell. `scripts/land-self-test` (`make gates`) runs it against
a forge in fixtures and a bare repository on disk.

- **A stack lands bottom first, one pull request at a time.** Land the bottom one, run the
  printed retarget for the one above it, land that, and so on. Nothing above a landed pull
  request is rebased or pushed: it keeps its commits, and its diff against `main` is the
  diff that was approved. GitHub may dismiss its approval when the base changes (community
  reports say it does, and that this is by design); `land/approved` then says so, and
  `scripts/land` approves the same head again after the keypress, with no rebase and no
  override. `main` must be an ancestor of the head when it is
  approved (`land/ancestor`): restack before approval, never after. A pull request that
  lands while a fix for a bug it carries waits further up names the bug under "Still
  waiting" in its "What merging this changes for FPL" section.
- **Never squash a multi-commit PR.** Squashing collapses the atomic commits, and their
  bodies and trailers, into one. (A one-commit PR is the only case where it is harmless.)
- After a landing, `git fetch github`: `github/main` is the landed head, and the branches of
  the pull requests above it are unchanged, so a local stack needs no restack.
- When the stack is empty, delete the `stack/…` refs, locally and on `github`. Nothing is lost:
  the grouping lives in each commit's `Stack:` trailer, the discussion in the PRs.

```
git log --grep='^Stack: typed-let$'       # the whole stack, years later, forge or no forge
```

"For now" is deliberate. PRs are the review surface because they are the one at hand, not
because the record belongs on a forge; rule 7 keeps the switch to an in-repo review system
cheap.

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
scripts/review --serve       import the open pull requests, then show them in the browser
```

stops the page this clone is already serving, if there is one, imports every open pull
request (`scripts/import-review --open`), and serves the patches on 127.0.0.1. The page
reads the patches and nothing else. Its address, token included, is also written to
`.git/review-serve.pid`, so it can be opened in another browser than the default.

Open pull requests form one queue, first in, first out: each is based on the one filed
before it, and only the head is based on main. The page is that queue as one surface, head
first, with the last few merged pull requests above it in grey. On the left is the queue as
a tree, main at the top, each pull request with its commits under it; a click on a pull
request scrolls there, a click on a commit shows that commit alone. On the right are the
timeline, the files and the commits of the pull request in view. `[` and `]` fold the two
panels away.

Every changed file is there whole. Long unchanged stretches are hatched in the gutter; a
click on the hatching folds one, `z` folds the one nearest you and `Z` all of them, but
nothing is folded unless you fold it. You read top to bottom and decide per hunk, in the
place you read it: approve with `→` or by dragging the hunk to the right, not this with `←`
or by dragging it to the left, comment with `c`. `↓` and `↑` move between hunks, `u` undoes
the last mark, and a selected range of lines can be approved on its own. A mark is a
Radicle reaction on those lines, signed like a comment. At the end of each pull request is
its merge button (`m`), which opens only when every hunk is approved; with hunks refused it
offers to request changes instead. Merging records your approval of the revision too, turns
the pull request purple and then grey, and moves on to the next one, which the merge has
moved onto the new main. An approval stays with a hunk as long as the hunk itself does not
change.

At the end of a pull request the page stops. Scroll on and a bar there fills; past the line
you are in the next pull request. The same going back up, into the ones already merged.

Only what is in Radicle shows; `scripts/review-serve` without `--fresh` serves it without
importing first. What you write there goes into the patch under your key, the way the
Radicle CLI writes it: a line comment into your review of the revision, a reply into the
thread it answers, accept or reject as your review's verdict. Comments in a review can be
resolved; imported ones cannot, because Radicle keeps them on the revision, where there is
no resolve, so they are answered instead.

```
scripts/export-review <number>... | --open
```

is the way back. What was written in the review and not imported goes onto the pull
request once, posted by the machine account: a line comment as a review comment on those
lines (or, for a line outside the forge's diff, a plain comment that names and links the
line), a reply to a forge comment as a reply in its thread, anything else and a verdict as a
comment. The first line names the writer and the key that signed it; the last is an HTML
comment with the Radicle id, which is how a second run skips it and how scripts/import-review
leaves it out. So a conversation can run in both places and each comment keeps one home.

The page also lands, one pull request at a time, but not yet as scripts/land does: it still
rebase-merges, which gives the commits new SHAs (see Land), so land with scripts/land
instead. A patch from a pull request at the bottom of its stack has an "approve and merge"
button: your gh account approves and rebase-merges it, but only while the forge still has the commit you reviewed
and its checks passed. The merge is then recorded in Radicle, the patches stacked on it
are replayed onto the new main and pushed as the machine account, and the landed branch is
deleted. An approved pull request among them is frozen (rule 10): pre-push refuses to move
it, and the page leaves it and those above it as they are, says so, and finishes the
landing. In a GitHub stack the forge moves them itself. Your checkout's main is left
alone. The server listens on 127.0.0.1 only and wants the token in the address it prints,
so no other page in the browser can write to it, or land.

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

## Why this and not a feature branch

A feature branch bundles N changes into one review. A stack keeps each change small enough to
review well, lets independent pieces land as soon as they're approved, and keeps `main`
history linear and bisectable. The cost — restacking on churn — is one command here.
