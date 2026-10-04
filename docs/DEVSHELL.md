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
| `gitleaks` | `scripts/leak-check`, which the hooks run on every commit and push (`docs/WORKFLOW.md`, rule 9), so it cannot be an opt-in layer |
| Python 3.12, `uv`, `ruff`, `pyright`, `make` | the implementation stack of `docs/STACK.md` and the gate of `docs/QUALITY.md`. `make` syncs Lark and the gate's Python tools into the worktree's `.venv` with `uv`, at the versions `quality/uv.lock` pins; several are not in nixpkgs. On Linux the shell also puts libstdc++ on `LD_LIBRARY_PATH`, which CrossHair's solver needs |

On first entry in a clone or worktree the shell runs `scripts/setup` (git hooks, stacked-commit
config, identity report). It checks `core.hooksPath` first, so every later entry is silent.

Not in the shell: credentials of any kind, and the `claude` CLI that the soft `atomic-check`
gate calls when it is present (the gate fails open without it, `docs/COMMITS.md`).

## Forge tools are opt-in

The default shell has no forge client; the harness runs on git alone (`docs/WORKFLOW.md`,
rule 7). Forge clients are **layers**, declared as data in `layers` in `flake.nix`;
`scripts/layer` lists them. Today: `github` (`gh`), `gitlab` (`glab`), `radicle` (`rad`,
`radicle-node`, `git-remote-rad`), `radicleui`, which `extends` `radicle` with the desktop
app for reviewing patches, and `forges`, which has no packages of its own and `extends` the
three clients.

Every combination of layers is a dev shell, named by the layer names in sorted order, joined
with `-`:

```
nix develop .#github -c gh pr create …
nix develop .#github-gitlab
```

With direnv, `scripts/layer` turns layers on and off for the checkout it is run in:

```
scripts/layer                    # list them; * marks the ones that are on here
scripts/layer on github gitlab   # direnv loads .#github-gitlab at the next prompt
scripts/layer off gitlab
scripts/layer reset              # back to .#default
```

It stores the choice in `.fpl-shell`, one layer per line, after checking each name against
the flake. The file is git-ignored, so the choice stays in one checkout. `.envrc` does not
trust it all the same: it reads the lines as names, never as code, cuts each down to
`[a-z0-9]`, and skips with an error whatever is not a layer of the flake.

## Your own tools on top

Tools a person wants that the project does not, an IPython or a profiler, do not go in the
flake: they go in `.envrc.local`, git-ignored, as direnv directives, for example
`use flake ~/dev/dotfiles#python`. `.envrc` sources it before its own `use flake`, so the
project's tools come first on PATH and a personal `python3` never shadows the pinned one.
Checked with two flakes on x86_64-linux, direnv 2.37.1: the project's Python 3.12 answered,
the personal shell's extra program was there.

To add a layer, add an entry to `layers`: a name of letters and digits, a `description`,
`packages`, and optionally `extends`. Nothing else needs editing. The flake flattens `extends`
and refuses a cycle or an unknown name with the path that led to it. The combination shells
are generated lazily, so an unused one costs nothing.

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
- **`aarch64-linux`** — built and exercised in an Ubuntu 22.04 VM on the maintainer's Mac,
  with Nix 2.35.2 unpacked into a home directory and mounted at `/nix` through `bwrap`, since
  the VM gives no root. Every tool resolves from the Nix store, `lark` 1.3.1 imports, `ruff`,
  `pyright` and `pytest` run on a Lark snippet, `.#default` has no `gh`, `.#github-gitlab`
  and `.#forges` have `gh` and `glab`, `scripts/layer` writes what direnv then loads.
  Intel Macs (`x86_64-darwin`) are not a target: nixpkgs 26.05 is the last release to support
  them.
- **Layers** — on `x86_64-linux` with direnv 2.37.1. No `.fpl-shell` loads `.#default`,
  without `gh`. `github` loads `.#github`; `gitlab` then `github`, unsorted, loads
  `.#github-gitlab` with both tools from the Nix store; `forges` gives both through `extends`.
  `radicle` gives `rad` 1.10.3, `radicleui` adds the `radicle-desktop` binary (not launched:
  no display there).
  Blank lines, comments, a missing final newline and a repeated name are fine. An unknown name
  and a line of shell metacharacters are skipped with the error and execute nothing. In the
  flake, a cycle, an unknown name in `extends` and a `-` in a layer name each stop evaluation
  with a message. `scripts/layer`: list, `on`, `off` and `reset` write what `.envrc` then
  loads; an unknown name and a name of shell metacharacters are refused before anything is
  stored; stray lines already in `.fpl-shell` are dropped at the next write.
- **Layers on the maintainer's `aarch64-darwin` Mac** — with direnv, each at its own prompt:
  `gitlab` then `github` in `.fpl-shell` loaded `.#github-gitlab`, with `gh`, `glab` and
  `ruff` from the Nix store; `gitlab` alone loaded `.#gitlab`, with `glab` from the store and
  `gh` falling back to the system one; `forges` loaded `.#forges`, with both from the store.
  The file was written by hand there; `scripts/layer` has not been run on that Mac.
- **"No `gh`" means none from this flake.** That Mac also has a `gh` in nix-darwin's system
  profile, so in the default shell `command -v gh` prints `/run/current-system/sw/bin/gh`. A
  dev shell prepends to `PATH`; it does not hide what the machine already has.

## Known trap: interactive `nix develop` on a Mac

direnv (above) is the recommended route into the shell — the trap below is what happens
without it.

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
