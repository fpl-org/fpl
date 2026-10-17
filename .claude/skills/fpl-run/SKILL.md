---
name: fpl-run
description: Run FPL with the walker - start the REPL, evaluate one expression, or run a .fpl file. Use when asked to run, try or demo FPL, to launch the app, or to see what an expression evaluates to.
---

The walker has two entries. The docs named below are the source of truth; this skill only
points at them.

In a checkout, the walker that `make check` judges, from the `.venv` (`AGENTS.md`, "To run
the walker"):

    make repl                          # the REPL; :quit leaves it
    make repl ARGS="-e '2 | 3 +'"      # one expression: prints 5
    make run FILE=path/to/p.fpl        # one file

Without the `.venv`, the same module tree as a Nix package, its dependencies from nixpkgs
(`.agents/DEVSHELL.md`, "The walker as a package"):

    nix run .# -- -e '2 | 3 +'         # from a clone: prints 5
    nix run github:fpl-org/fpl         # anywhere: main's walker, no clone

Everything after `--` (or in `ARGS`) goes to `python -m fpl.repl`; a wrong argument prints its
usage line and exits 2.
