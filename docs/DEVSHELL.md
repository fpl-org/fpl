# DEVSHELL.md — one environment for everyone

`flake.nix` defines a single [Nix](https://nixos.org) dev shell for the harness and for every
implementation worktree. Entering it gives a human or an agent the same tools at the same
versions, on macOS and Linux, without installing anything globally.

```
nix develop            # enter the shell once
direnv allow           # or: load it automatically on cd (see below)
```

It needs Nix with flakes enabled (`experimental-features = nix-command flakes`). Nothing else:
no Homebrew, no pyenv, no global pip.

## Loading it automatically

`.envrc` holds one directive, `use flake`, which makes [direnv](https://direnv.net) load the
shell whenever you `cd` into the repository or one of its worktrees and unload it when you
leave. direnv's own description: "Load the build environment of a derivation similar to
`nix develop`." Run `direnv allow` once per checkout; direnv will not execute an `.envrc` it
has not been shown, and asks again when the file changes. Worktrees branch from `main`, so
each carries its own `.envrc` and needs its own `direnv allow`.

Plain `use flake` re-evaluates the flake when `flake.nix` or `flake.lock` change. If entering
feels slow, [nix-direnv](https://github.com/nix-community/nix-direnv) caches the result and
keeps it from being garbage-collected; it needs no change here. `.direnv/` is git-ignored.

Editors and agents started from a shell with direnv active inherit the environment. One
started elsewhere does not: launch it from the repo directory, or wrap the command as
`nix develop -c <command>`.

## What is in it, and why

| Tools | Why |
| --- | --- |
| `bash` 5, GNU `coreutils` `grep` `sed` `awk` | `scripts/` and `.githooks/` need bash ≥ 4 (`mapfile`) and were written against GNU userland; macOS ships bash 3.2 and BSD tools |
| `git`, `gh`, `jj` | the workflow of `docs/WORKFLOW.md`; `jj` is the optional one of `docs/JJ.md` |
| Python 3.12 with `lark` and `pytest`, `ruff`, `pyright`, `make` | the implementation stack of `docs/STACK.md` and the `make check` gate of `docs/CONVENTIONS.md`, with no virtualenv to create first |

On first entry in a clone or worktree the shell runs `scripts/setup` (git hooks, stacked-commit
config, identity report). It checks `core.hooksPath` first, so every later entry is silent.

Not in the shell: credentials of any kind, and the `claude` CLI that the soft `atomic-check`
gate calls when it is present (the gate fails open without it, `docs/COMMITS.md`).

## nixpkgs comes from nixos.org, not from a forge

The usual flake input is `github:NixOS/nixpkgs/…`. This flake takes the channel tarball from
`channels.nixos.org` instead. The channel URL moves, but `nix flake lock` follows it to the
immutable `releases.nixos.org` tarball and records that URL, the nixpkgs revision and the
content hash in `flake.lock`, so the pin is as strict as a forge input. The difference is that
the environment keeps working when GitHub is unreachable or not allowed — a locked-down CI
runner, an agent sandbox that only admits selected repositories — which is the same reason the
repository keeps its records in-repo (`docs/WORKFLOW.md`, rule 7).

Update deliberately, as its own commit: `nix flake update`, then `make check` in a worktree.
`nix fmt` formats `flake.nix`.

## What was verified

The shell was built and exercised on `x86_64-linux`: every tool above resolves from the Nix
store, `ruff`, strict `pyright` and `pytest` pass on a Lark snippet, and the first-entry hook
wires a fresh clone and then stays silent. For `aarch64-darwin`, `x86_64-darwin` and
`aarch64-linux` the shell was evaluated down to its derivation — every package exists for them
— but not built. The first person to enter it on a Mac is the test.
