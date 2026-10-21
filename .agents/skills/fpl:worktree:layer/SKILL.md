---
name: fpl:worktree:layer
description: Turn the opt-in layers of the dev shell (the forge clients gh, glab, rad) on and off for this checkout with the layer script of this skill. Use when a script refuses with "gh is not on PATH" or "rad not found", before land, task or the Radicle review scripts, and to see which layers are on.
---

The default dev shell has no forge client: the harness runs on git alone, and each client is
a layer declared in `flake.nix` (the design and what was measured: `.agents/DEVSHELL.md`,
"Forge tools are opt-in"). Today: `github` (`gh`), `gitlab` (`glab`), `radicle` (`rad`,
`radicle-node`, `git-remote-rad`), `radicleui`, which extends `radicle` with the desktop app,
and `forges`, which extends the three clients.

    .agents/skills/fpl:worktree:layer/scripts/layer                  list; * marks what is on
    .agents/skills/fpl:worktree:layer/scripts/layer on github gitlab
    .agents/skills/fpl:worktree:layer/scripts/layer off gitlab
    .agents/skills/fpl:worktree:layer/scripts/layer reset            back to .#default

It writes the git-ignored `.fpl-shell` at the top of the checkout, one layer per line, after
checking each name against the flake; direnv loads the shell named by the layers in sorted
order (`.#github-gitlab`) at the next prompt. One checkout, one choice.

- **Exit 0**: the last line says which layers are on and which shell direnv loads next.
- **Exit 1**: nothing was written. The message names the cause: an unknown layer (the list
  shows the names), no checkout, or a flake that would not evaluate.

Without direnv, or for one command, skip the file: `nix develop .#github -c gh ...`.
