# .agents/skills — the skills of this repository, the source of its procedures

A skill says when and how to run one script: its arguments, its exit codes, what comes next.
One directory per skill, `<name>/SKILL.md`, the frontmatter `name` equal to the directory. Names
are `fpl:<module>[:<skill>[:<sub>]]`; the layers live in the name and the directories stay flat,
because Claude Code reads no nested directories. A routine skill (`fpl:present`) is a step list
of sub-skills, each loaded by name. A script a skill owns lives in `<name>/scripts/`.

Codex and Cursor read this directory as it is. Claude Code reads `.claude/skills`, which is one
symbolic link here. The tree, and what is planned: `AGENTS.md`.
