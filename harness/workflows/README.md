# harness/workflows

Drafts of workflows that only the owner installs. An agent's token cannot push a file under
`.github/workflows` (it has no `workflow` scope), and `scripts/land` refuses a range that
touches one (`land/workflows`), so each draft lives here until the owner copies it over,
reads the diff and pushes it to main himself.

## land.yml

The lander: `workflow_dispatch` on main with input `pr`, a verify job without secrets and a
land job in the environment `land` that runs `scripts/land --ci` with the fpl-lander App's
token. It needs the environment `land` (policy: main only) holding the secrets
`LAND_APP_ID` and `LAND_APP_KEY`, and fpl-lander in each ruleset's bypass list on main with
mode Always. Install, from a clean checkout of main:

    cp harness/workflows/land.yml .github/workflows/land.yml && git add .github/workflows/land.yml && git commit -m "ci(land): install the lander"

Then run it once by hand: Actions > land > Run workflow, `pr` = an approved pull request.
