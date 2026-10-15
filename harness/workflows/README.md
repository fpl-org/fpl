# harness/workflows

Drafts of workflows that only the owner installs. An agent's token cannot push a file under
`.github/workflows` (it has no `workflow` scope), and `scripts/land` refuses a range that
touches one (`land/workflows`), so each draft lives here until the owner copies it over,
reads the diff and pushes it to main himself.

## land.yml

The lander: `workflow_dispatch` on main with input `pr`, a verify job without secrets and a
land job in the environment `land` that runs `scripts/land --ci` with the fpl-lander App's
token. It needs:

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
