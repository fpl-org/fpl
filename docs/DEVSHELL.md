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

- **`x86_64-linux`** — built and exercised: every tool above resolves from the Nix store,
  `ruff`, strict `pyright` and `pytest` pass on a Lark snippet, and the first-entry hook wires
  a fresh clone and then stays silent.
- **`aarch64-darwin`** — built on the maintainer's Mac. `nix develop -c …` resolves `git`,
  `python3`, `ruff` and `pyright` from the Nix store and imports `lark` 1.3.1.
- **`x86_64-darwin`, `aarch64-linux`** — evaluated down to the derivation (every package
  exists for them), not built.

## Known trap: interactive `nix develop` on a Mac

On that same Mac, a bare interactive `nix develop` gave a half-working shell: `bash`, `make`,
`sed`, `grep` and `awk` came from the Nix store, but `git` and `gh` resolved to nix-darwin's
system profile, `jj` and `python3` to Homebrew, and `ruff` and `pyright` were not found at all,
so `import lark` failed. The identical flake run as `nix develop -c <command>` was correct, so
the flake is not at fault: the interactive shell's own startup files rewrite `PATH` after Nix
has set it. Which file does it has not been tracked down.

Until it is, do not trust a bare `nix develop` prompt on macOS. Use direnv (above), which
applies the environment from the prompt hook, after the startup files have run, and without a
nested shell — or run things as `nix develop -c <command>`. A quick self-check in any shell:
`command -v ruff` must print a `/nix/store/…` path.
