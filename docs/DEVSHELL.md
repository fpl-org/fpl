# DEVSHELL.md — one environment for everyone

`flake.nix` defines one [Nix](https://nixos.org) dev shell for the harness and for every
implementation worktree. Entering it gives a human or an agent the same tools at the same
versions, on macOS and Linux, without installing anything globally. Forge clients are opt-in
layers on top of it ([below](#forge-tools-are-opt-in)).

```
nix develop            # enter the shell once
direnv allow           # or: load it automatically on cd (see below)
```

It needs Nix with flakes enabled (`experimental-features = nix-command flakes`). Nothing else:
no Homebrew, no pyenv, no global pip.

## Loading it automatically

`.envrc` ends in one directive, `use flake`, which makes [direnv](https://direnv.net) load the
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
| `git`, `jj` | the workflow of `docs/WORKFLOW.md`; `jj` is the optional one of `docs/JJ.md` |
| Python 3.12 with `lark` and `pytest`, `ruff`, `pyright`, `make` | the implementation stack of `docs/STACK.md` and the `make check` gate of `docs/CONVENTIONS.md`, with no virtualenv to create first |

On first entry in a clone or worktree the shell runs `scripts/setup` (git hooks, stacked-commit
config, identity report). It checks `core.hooksPath` first, so every later entry is silent.

Not in the shell: credentials of any kind, and the `claude` CLI that the soft `atomic-check`
gate calls when it is present (the gate fails open without it, `docs/COMMITS.md`).

## Forge tools are opt-in

The default shell holds no forge client. Everything the harness does itself — the hooks, the
linters, `acommit`, `restack` — runs on git alone, and rule 7 of `docs/WORKFLOW.md` wants it to
stay that way. A program whose only use is talking to one company's API is not something every
checkout should load whether it needs it or not.

`gh` is still the practical way to file the pull requests of `docs/WORKFLOW.md`, "Land —
through GitHub, for now". So it is a **layer**: a package of the flake, from the same nixpkgs
pin, that goes on top of the default shell when a checkout asks for it.

| Layer | Tool |
| --- | --- |
| `github` | `gh` |

With direnv, name the layers in `.fpl-shell`, one per line; `#` starts a comment:

```
echo github > .fpl-shell        # picked up at the next prompt
rm .fpl-shell                   # back to no forge tooling
```

Without direnv:

```
nix develop .#github -c gh pr create …           # the default shell plus one layer
nix develop -c nix shell .#github -c gh …        # the general form; `nix shell` takes any
                                                 # number of layers
```

Layers, not alternative shells, because forges add up: a checkout that pushes to two of them
wants both clients, and one shell per combination doubles with every forge. `.envrc` always
loads the default shell and then puts each requested layer in front of `PATH`, so any
combination is one more line in `.fpl-shell`. The layers are built in one `nix build`, with
out-links under `.direnv/` as garbage-collector roots; `PATH` gets the store paths
themselves, so `command -v gh` still shows where the tool comes from.

`.fpl-shell` is git-ignored: the choice belongs to one checkout and never travels with a
commit, so nobody gets a forge client because somebody else wanted one. The file holds names,
not code. `.envrc` reads it line by line, strips everything outside `[a-z0-9-]`, and accepts
only the layers it knows; anything else is skipped with an error and the rest still loads. It
is deliberately not sourced: direnv asks for approval of `.envrc` itself, but not of files an
`.envrc` sources, so a sourced, git-ignored file would be a way to run code nobody reviewed.

A new layer is two edits: an entry in `layers` in `flake.nix`, and its name in the `case` of
`.envrc`. The `nix develop .#<layer>` shells are generated from `layers`.

## nixpkgs comes from nixos.org, not from a forge

The usual flake input is `github:NixOS/nixpkgs/…`. This flake takes the channel tarball from
`channels.nixos.org` instead. The channel URL moves, but `nix flake lock` follows it to the
immutable `releases.nixos.org` tarball and records that URL, the nixpkgs revision and the
content hash in `flake.lock`, so the pin is as strict as a forge input. The difference is that
the environment keeps working when GitHub is unreachable or not allowed — a locked-down CI
runner, an agent sandbox that only admits selected repositories — which is the same reason the
repository keeps its records in-repo (`docs/WORKFLOW.md`, rule 7).

Update deliberately, as its own commit: `nix flake update`, then `make check` in a worktree.
`nix fmt flake.nix` formats it.

## What was verified

- **`x86_64-linux`** — built and exercised: every tool above resolves from the Nix store,
  `ruff`, strict `pyright` and `pytest` pass on a Lark snippet, and the first-entry hook wires
  a fresh clone and then stays silent.
- **`aarch64-darwin`** — built on the maintainer's Mac. Both `nix develop -c …` and direnv
  (`direnv allow`, then the next prompt in zsh) resolve `git`, `python3` and `ruff` from the
  Nix store and import `lark` 1.3.1.
- **`x86_64-darwin`, `aarch64-linux`** — evaluated down to the derivation (every package
  exists for them), not built.
- **The `github` layer** — on `x86_64-linux` with direnv 2.37.1: no `.fpl-shell` gives no
  `gh`; `github` gives `gh` from the Nix store next to an unchanged `ruff` and `git`; blank
  lines, comments, a missing final newline and a name given twice are fine; an unknown name
  and a line of shell metacharacters are skipped with the error and execute nothing; removing
  the file removes the roots under `.direnv/`. `nix develop -c nix shell .#github` and
  `nix develop .#github` work too. On the other three systems the layer is evaluated, not
  built. Its predecessor, a whole `github` shell chosen by one name in `.fpl-shell`, was
  built and switched on the maintainer's `aarch64-darwin` Mac; the layered form has not been
  run there yet.
- **"No `gh`" means none from this flake.** That Mac also has a `gh` in nix-darwin's system
  profile, so in the default shell `command -v gh` prints `/run/current-system/sw/bin/gh`. A
  dev shell prepends to `PATH`; it does not hide what the machine already has.

## Known trap: interactive `nix develop` on a Mac

On that same Mac, a bare interactive `nix develop` gave a half-working shell: `bash`, `make`,
`sed`, `grep` and `awk` came from the Nix store, but `git` and `gh` (then still in the default
shell) resolved to nix-darwin's system profile, `jj` and `python3` to Homebrew, and `ruff` and
`pyright` were not found at all, so `import lark` failed. The identical flake run as
`nix develop -c <command>` was correct, so the flake is not at fault: the interactive shell's
own startup files rewrite `PATH` after Nix has set it. Which file does it has not been tracked
down.

Until it is, do not trust a bare `nix develop` prompt on macOS. Use direnv (above), which
applies the environment from the prompt hook, after the startup files have run, and without a
nested shell — on that Mac it gave the correct environment where the interactive shell did
not — or run things as `nix develop -c <command>`. direnv applies the change at the *next*
prompt: a check typed together with `direnv allow` still sees the old `PATH`. A quick
self-check in any shell:
`command -v ruff` must print a `/nix/store/…` path.
