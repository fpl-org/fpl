# harness/workflows

Drafts of workflows that only the owner installs. An agent's token cannot push a file under
`.github/workflows` (it has no `workflow` scope), and `scripts/land` refuses a range that
touches one (`land/workflows`), so each draft lives here until the owner copies it over,
reads the diff and pushes it to main himself.

## land.yml

The lander: `workflow_dispatch` on main with input `pr`, a verify job without secrets and a
land job in the environment `land` that runs `scripts/land --ci` with the fpl-lander App's
token. When main is no ancestor of the dispatched head (a sister landed first), verify
relocates it onto main, runs `make quick` on each pick and `make check` on the tip; land
derives the relocation again and lands it on the approval of the old head when every commit
kept its patch id and message, else publishes it as `<head>-relocated` and asks for a
review (`scripts/land --verify`, `--relocate`). It needs:

- the environment `land` (policy: main only) holding the secrets `LAND_APP_ID` and
  `LAND_APP_KEY`;
- the App's repository permissions Contents, Pull requests and Checks write and Commit
  statuses read (a token cannot ask for a permission the installation lacks);
- fpl-lander in each ruleset's bypass list on main with mode Always;
- Settings > General > Pull Requests > "Automatically delete head branches" off: GitHub would
  delete a landed branch before its children are retargeted, which closes them.
  `scripts/land --ci` refuses (`land/autodelete`) while it is on; check with
  `gh api repos/fpl-org/fpl --jq .delete_branch_on_merge`, which must print `false`.

Install, from a checkout with `github/main` fetched. The commit goes on a detached HEAD,
since the hooks keep `main` itself where `github/main` is, and the push is the owner's direct
push to main. The commit is the owner's own, so its message carries `Human-Only: true`: without
it, or an agent's `Assisted-By` and `Session-Id`, `.githooks/commit-msg` refuses it
(`scripts/land-self-test` runs the hook on this line's message):

    git checkout --detach github/main && cp harness/workflows/land.yml .github/workflows/land.yml && git add .github/workflows/land.yml && git commit -m "ci(land): install the lander" -m "Human-Only: true" && git push github HEAD:refs/heads/main && git checkout main

Then run it once by hand: Actions > land > Run workflow, `pr` = an approved pull request. A
run lands at most one pull request and starts no other run. The relay job of `series.yml`
(drafted in #168, not installed) dispatches a run on each approval by the owner; until it is
installed, each landing is a dispatch by hand.

## brake.yml

The lock of the cap (`.agents/WORKFLOW.md`, "The cap"). On each pull request event, every
15 minutes and on each push to main, `scripts/wip-count` counts the open work and
`scripts/brake-flip` sets the ruleset `brake: all branches except main` to match. The job
summary gives the count, the decision and the lag from the event. Install (owner), once that
ruleset exists and the environment `brake` holds the secrets `BRAKE_APP_ID` and
`BRAKE_APP_KEY` (the fpl-brake App's id and private key):

```
cp harness/workflows/brake.yml .github/workflows/brake.yml
```

Give the environment `brake` no required reviewers and no wait timer: a protection rule
holds every run until someone approves it.

The push that lands the copy on main is itself a run, and a live one: only a run started
by hand can be a dry run. If the ruleset differs from what the count asks, that first run
writes it. To see a dry run first, land the copy with its `on:` cut down to
`workflow_dispatch`, run it by hand with dry run on, read the summary, then add the other
triggers back.

- Proven: the App flips `enforcement` with a PUT of that field alone, in 13 s median and
  21 s at most from the event.
- Not yet proven: a PUT that also carries `conditions` keeps `rules` and `bypass_actors`.
  The summary prints both before and after each write; read it on the first live flip.
- `app-id` is deprecated for `client-id` in the pinned token action; it still works.

## series.yml

Install (owner):

```bash
git mv harness/workflows/series.yml harness/workflows/series-relay.yml .github/workflows/
```

Both need `scripts/present-check` on `main` first.

- `series.yml` judges each push lemma by lemma and comments. Its required check, once marked
  so, is `lemmas`.
- `series-relay.yml` relays the owner's approval to `land.yml`. It is a workflow of its own
  because every workflow that listens to `pull_request_review` starts on each review, and a job
  skipped there would report success under the name of a check a push had judged red. It fails,
  harmlessly, until `land.yml` is on `main`, and always for a pull request from a fork, whose
  run GitHub denies `actions: write`: there the error names the `land.yml` run to start by hand.
