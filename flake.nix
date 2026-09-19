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
    in
    {
      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = [
            # The harness: scripts/ and .githooks/ are bash >= 4 (mapfile) and were written
            # against GNU userland; macOS ships bash 3.2 and BSD tools.
            pkgs.bashInteractive
            pkgs.coreutils
            pkgs.gnugrep
            pkgs.gnused
            pkgs.gawk
            pkgs.git
            pkgs.gh
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
      });

      formatter = forAllSystems (pkgs: pkgs.nixfmt);
    };
}
