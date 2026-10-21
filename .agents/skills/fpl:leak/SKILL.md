---
name: fpl:leak
description: Judge text or commits for private terms and secrets before they leave the machine, with the leak-check script of this skill. Use on a pull-request body, a review card, a task title or any text bound for the public forge (--text), and on a range of commits (--range); the hooks run it on every commit and push by themselves.
---

The repository is public, and so is whatever a commit, a push or a pull request carries. One
script judges all of it, with gitleaks, against two sets of rules: gitleaks's defaults, which
find keys and tokens, and a private list of terms that is never committed (the policy and the
lists: `.agents/WORKFLOW.md`, rule 9).

    .agents/skills/fpl:leak/scripts/leak-check --text FILE      free text bound for the forge
    .agents/skills/fpl:leak/scripts/leak-check --range REVS     every commit REVS names
    .agents/skills/fpl:leak/scripts/leak-check --self-test      its proof, in a temp repo

The hooks run the other modes without being asked: `--staged` in pre-commit, `--message` in
commit-msg, `--push` in pre-push. Run `--text` yourself on every body you are about to post
(a card, a pull-request body, an issue, a task title) and `--range` on a branch before it is
pushed by a tool that skips the hooks.

- **Exit 0**: nothing found. Post or push.
- **Exit 1**: something found, or the check could not run (gitleaks failed while a private
  list exists, or a step of its own failed). The report names the rule and the list line it
  came from, and where (commit, file, line), never the term. Remove it and run again; a
  check that could not run is a stop, not a pass.

`FPL_LEAK_GATE=warn` reports without refusing, `off` skips; neither is for text that goes
out. With no list and no gitleaks the script warns and passes: enter the dev shell
(`nix develop`), which has gitleaks.

Loaded by the present, pr and task skills before anything of theirs reaches the forge.
