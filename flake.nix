{
  description = "FPL: one dev shell for the harness and every implementation worktree";

  # nixpkgs straight from nixos.org, not from a forge. The channel URL moves, but
  # `nix flake lock` pins the immutable releases.nixos.org tarball behind it (revision
  # and hash are in flake.lock), so the environment does not depend on GitHub being
  # reachable. Bump with `nix flake update`.
  inputs.nixpkgs.url = "https://channels.nixos.org/nixos-26.05/nixexprs.tar.xz";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "aarch64-darwin"
        "x86_64-darwin"
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});

      layers = pkgs: {
        github = pkgs.gh;
        gitlab = pkgs.glab;
      };
    in
    {
      # Opt-in layers: tools that talk to one forge. None of them is in the default shell
      # (docs/DEVSHELL.md). Each is a package, so they stack in any combination: several
      # installables to `nix shell`, or one name per line in the git-ignored .fpl-shell for
      # direnv. .envrc keeps a list of these names; add a layer in both places.
      packages = forAllSystems layers;

      devShells = forAllSystems (
        pkgs:
        let
          # Everything the harness and an implementation worktree need, and nothing that
          # talks to a forge: the default shell must be enough to do all the work offline
          # and against any remote.
          base = [
            # The harness: scripts/ and .githooks/ are bash >= 4 (mapfile) and were written
            # against GNU userland; macOS ships bash 3.2 and BSD tools.
            pkgs.bashInteractive
            pkgs.coreutils
            pkgs.gnugrep
            pkgs.gnused
            pkgs.gawk
            pkgs.git
            pkgs.jujutsu # optional workflow, docs/JJ.md

            # The implementation stack, docs/STACK.md: Python 3.12 + Lark, and the
            # `make check` gate of docs/CONVENTIONS.md (ruff, pyright strict, pytest).
            (pkgs.python312.withPackages (ps: [
              ps.lark
              ps.pytest
            ]))
            pkgs.ruff
            pkgs.pyright
            pkgs.gnumake
          ];

          mkFplShell =
            extra:
            pkgs.mkShell {
              packages = base ++ extra;

              # Wire the git hooks once per clone/worktree; stay silent afterwards so that
              # direnv re-entering the shell costs nothing.
              shellHook = ''
                if top="$(git rev-parse --show-toplevel 2>/dev/null)" \
                  && [ -x "$top/scripts/setup" ] \
                  && [ "$(git config --local --get core.hooksPath 2>/dev/null)" != ".githooks" ]; then
                  "$top/scripts/setup"
                fi
              '';
            };
        in
        # `nix develop .#github` and so on: the default shell plus that one layer, for a
        # single command without direnv. Generated from `layers`, so the two cannot drift.
        nixpkgs.lib.mapAttrs (_: layer: mkFplShell [ layer ]) (layers pkgs)
        // {
          default = mkFplShell [ ];
        }
      );

      formatter = forAllSystems (pkgs: pkgs.nixfmt);
    };
}
