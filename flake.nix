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
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});

      # Opt-in layers on top of the default shell. DATA ONLY: a name (letters and digits),
      # a description, packages, and optionally `extends`, naming layers whose packages come
      # along. Today every layer is a forge client, because nothing that talks to a forge
      # belongs in the default shell (docs/DEVSHELL.md). To add a layer, add an entry here;
      # the shells and the list .envrc checks against are generated below.
      layers = pkgs: {
        github = {
          description = "GitHub's CLI (gh)";
          packages = [ pkgs.gh ];
        };
        gitlab = {
          description = "GitLab's CLI (glab)";
          packages = [ pkgs.glab ];
        };
        radicle = {
          description = "Radicle's CLI and node (rad, radicle-node, git-remote-rad)";
          packages = [ pkgs.radicle-node ];
        };
        radicleui = {
          description = "Radicle's desktop app, for reviewing patches; large";
          extends = [ "radicle" ];
          packages = [ pkgs.radicle-desktop ];
        };
        forges = {
          description = "every forge client (not the desktop app)";
          extends = [
            "github"
            "gitlab"
            "radicle"
          ];
          packages = [ ];
        };
      };

      # Flattens `extends` into one package list per layer, so nothing downstream knows about
      # inheritance. The graph may be a DAG; `unique` drops what is reached twice. A cycle or
      # an unknown name throws with the path that led there. Plain recursion would instead
      # hang the evaluator, which looks like a wedged machine rather than a bad config.
      resolveLayers =
        raw:
        let
          inherit (nixpkgs.lib)
            concatMap
            concatStringsSep
            elem
            hasInfix
            mapAttrs
            unique
            ;
          packagesOf =
            seen: name:
            if elem name seen then
              throw "layer cycle: ${concatStringsSep " -> " (seen ++ [ name ])}"
            else if !(raw ? ${name}) then
              throw "unknown layer '${name}', named by: ${concatStringsSep " -> " seen}"
            else
              let
                layer = raw.${name};
                inherited = concatMap (packagesOf (seen ++ [ name ])) (layer.extends or [ ]);
              in
              inherited ++ layer.packages;
          badNames = builtins.filter (hasInfix "-") (builtins.attrNames raw);
        in
        if badNames != [ ] then
          throw "a layer name may not contain '-', which joins names: ${toString badNames}"
        else
          mapAttrs (name: layer: {
            inherit (layer) description;
            packages = unique (packagesOf [ ] name);
          }) raw;
    in
    {
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
        # One shell per combination of layers, named by the layer names in sorted order joined
        # with "-": default, github, github-gitlab, ... Attributes are lazy, so a combination
        # nobody asks for is never evaluated. .envrc builds the same name from .fpl-shell.
        let
          inherit (nixpkgs.lib) concatMap foldl unique;
          resolved = resolveLayers (layers pkgs);
          names = builtins.attrNames resolved;
          subsets = foldl (acc: n: acc ++ map (s: s ++ [ n ]) acc) [ [ ] ] names;
          shellFor = subset: {
            name = if subset == [ ] then "default" else builtins.concatStringsSep "-" subset;
            value = mkFplShell (unique (concatMap (n: resolved.${n}.packages) subset));
          };
        in
        builtins.listToAttrs (map shellFor subsets)
      );

      # What layers exist, without building anything: `nix eval --json .#lib.layers`.
      # .envrc checks .fpl-shell against `layerNames`. Only names and descriptions are forced,
      # so the empty package set is never looked into.
      lib.layers = builtins.mapAttrs (_: layer: layer.description) (layers { });
      lib.layerNames = builtins.concatStringsSep " " (builtins.attrNames (layers { }));

      formatter = forAllSystems (pkgs: pkgs.nixfmt);
    };
}
