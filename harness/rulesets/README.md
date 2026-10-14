# harness/rulesets

The repository rulesets of fpl-org/fpl as files, so a change to one is a diff someone reviews
and `scripts/ruleset-check` can say when the forge no longer matches.

- `brake.json`: `brake: all branches except main`, to import; it ships disabled.
- `main-pr-only-linear.json`, `main-review-blockers.json`: exports of the two live rulesets
  of main. `exports-note.txt` says what they leave out (`bypass_actors`) and why.

## The brake

On every branch except `main` the brake refuses creating a ref and updating one
(`update_allows_fetch_and_merge` false), for everyone but the repository admin role and the
fpl-lander app. `psjg-claude` and `psjg-codex` are not bypass actors, so with the brake active
their pushes of new and existing branches are refused. It is the ruleset proven on
fpl-org/harness-proef.

Import it (owner): Settings > Rules > Rulesets > New ruleset > Import a ruleset, and choose
`harness/rulesets/brake.json`. The form should fill in the name, enforcement Disabled, all
branches but `main`, the rules "Restrict creations" and "Restrict updates", and the two bypass
actors (both "Always allow"). Create it: nothing is enforced yet. To switch the brake on, set
Enforcement status to Active.

Above the cap the flipper that switches it on will have to exclude the heads of open pull
requests, so that fixes on a pull request he asked changes for stay pushable: with the brake
as it is here every branch but `main` is locked. A later unit measures and builds that.

## Checking

    scripts/ruleset-check          # exit 0 in sync, 1 drift, 2 cannot read; --json for machines

It only reads. As the machine account: `GH_TOKEN=$(gh auth token --user psjg-claude)`. Until
`brake.json` is imported it reports the brake as `NOT LIVE` and exits 1. Its proof is
`scripts/ruleset-check-self-test`, run by `make gates`.
