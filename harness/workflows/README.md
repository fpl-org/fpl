# harness/workflows

Drafts of GitHub Actions workflows, kept here because an agent's token cannot push under
`.github/workflows/` (`.agents/WORKFLOW.md`, rule 8). To install `series.yml`, the owner runs
`git mv harness/workflows/series.yml .github/workflows/series.yml` and pushes it himself. It
needs `scripts/present-check` on `main` first, and its `relay` job fails, harmlessly, until
`land.yml` is on `main`, and always for a pull request from a fork, whose run GitHub denies
`actions: write`: there the error names the `land.yml` run to start by hand. Its required
check, once marked so, is `lemmas`.
