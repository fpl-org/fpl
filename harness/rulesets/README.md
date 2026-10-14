# harness/rulesets

The repository rulesets of fpl-org/fpl as files, so a change to one is a diff someone reviews
and `scripts/ruleset-check` can say when the forge no longer matches.

- `main-pr-only-linear.json`, `main-review-blockers.json`: exports of the two live rulesets
  of main. `exports-note.txt` says what they leave out (`bypass_actors`) and why.
