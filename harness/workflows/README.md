# harness/workflows

Workflows drafted by agents, kept here because an agent's token cannot push
`.github/workflows/` (`.agents/WORKFLOW.md`, rule 8). A draft runs nowhere until the owner
copies it there; the copy is his review.

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
holds every run until someone approves it. First run: by hand, with dry run on.

- Proven: the App flips `enforcement` with a PUT of that field alone, in 13 s median and
  21 s at most from the event.
- Not yet proven: a PUT that also carries `conditions` keeps `rules` and `bypass_actors`.
  The summary prints both before and after each write; read it on the first live flip.
- `app-id` is deprecated for `client-id` in the pinned token action; it still works.
