---
name: fpl:land:dry-run
description: Make every check the lander makes on a pull request, changing nothing on the forge, with scripts/land --dry-run. Use before asking for a landing, after a push to an approved head, and whenever the lander refused and you want the rule named.
---

    nix develop .#github -c scripts/land --dry-run <number>

`gh` is in the github layer of the dev shell, not the default one: this enters it for the
one command, and with direnv the layer script's `layer on github` turns it on for the
checkout (`.agents/DEVSHELL.md`). It reads the forge as it is, fetches the head and `main`
into this clone, and prints one line per rule, `ok`, `NO` with its remedy, or `--`
when an answer the rule rests on is missing; then the approval it would give, the exact
push, the retarget of what is stacked on the head, and the `git ls-remote` that shows
`main` is the head afterwards. The rules and what each wants are the header of
`scripts/land` (`land/open` to `land/remote`); `land/size` is 10 commits and 600 lines, and a
pull request over it is split, not rewritten.

- **Exit 0**: every rule holds; hand the number to `fpl:land:land`.
- **Exit 1**: a rule refused. Do not land. The remedy is in the line; `land/workflows` routes
  the landing to the owner's key, the others name what to fix or whom to ask.
- **Exit 2**: usage; `--ci` rules (`land/ci`, `land/autodelete`) are not judged here.
