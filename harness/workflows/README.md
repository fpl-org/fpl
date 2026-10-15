# harness/workflows

Drafts of GitHub Actions workflows, kept here because an agent's token cannot push under
`.github/workflows/` (`.agents/WORKFLOW.md`, rule 8). The owner installs them himself:

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
