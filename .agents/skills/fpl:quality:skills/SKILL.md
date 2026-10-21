---
name: fpl:quality:skills
description: Hold the skill tree whole and every script the prose names under a skill, with scripts/skills-cover. Use after writing or moving a skill, a script, or a paragraph that names one, before a push, and to shrink quality/skills-ratchet.
---

A procedure lives in a skill, not in prose; the prose keeps decisions. Run, from any checkout:

    .agents/skills/fpl:quality:skills/scripts/skills-cover

It reads AGENTS.md, `.agents/*.md`, `.claude/agents/*.md` and `.claude/commands/*.md`, and refuses:

- `SKILLS-UNCOVERED`: a `scripts/<x>` or `.agents/skills/<s>/scripts/<x>` that exists, stands in
  that prose, and no `SKILL.md` names (a `*-self-test` is a proof, never counted), unless
  `quality/skills-ratchet` lists it as `<path> -- <reason>`.
- `SKILLS-RATCHET-STALE`, `SKILLS-RATCHET-REASON`: a ratchet line for a script a skill names
  now or that is gone; a line without its reason. The list only shrinks.
- `SKILLS-NAME`: a skill directory without `SKILL.md`, or whose frontmatter `name` is not the
  directory, or not `fpl:<module>[:<skill>[:<sub>]]` in `[a-z0-9-]`.
- `SKILLS-LINK`: `.claude/skills` is not a symbolic link to `../.agents/skills`.
- `SKILLS-SUB`: a `SKILL.md` names a skill `fpl:...` that has no directory.
- `SKILLS-SCREEN`: AGENTS.md over 80 lines.

Every refusal prints its rule, what, and the remedy. Exit 0 clean; 1 refused; 2 usage; 3 when
git cannot say where the root is (name it: `skills-cover <root>`).

To shrink the ratchet, write the skill that names the script, then delete its line; the gate
refuses the line once it is stale, so nothing is forgotten. To see what the tree still owes:

    .agents/skills/fpl:quality:skills/scripts/skills-cover --uncovered

prints one line per uncovered script, with the reason the ratchet gives it today, else none
after ` --`: write the reason yourself (the unit that converts it), never a placeholder.

`make gates` runs `scripts/skills-cover-self-test` beside it, found by `scripts/gates-list`:
every rule on a good and a bad fixture, under `/bin/bash` and the bash on PATH, then a replay
over this tree (0 refusals with the ratchet, N without) and over every open pull request tip
the forge lists, printing what each tip must add when it lands on this gate.
