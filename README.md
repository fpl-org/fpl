---
title: Readme
marimo-version: 0.23.10
width: full
---

```python {.marimo name="setup"}
import marimo as mo; import fpl
```

# FPL

Dit is de homepage van de repo. Hiervanaf kan je gaan verkennen.

## Goal

FPL should maximize the capacity it affords its operators to achieve their goals per unit of complexity and effort.

Those goals: solving problems by making fast, efficient, safe and ergonomic software.

## What FPL is

A two-level language (2LTT [1]): a fixed meta level over an object level whose
theory is pluggable. The default object theory is call-by-push-value (CBPV [2]).
Terms are abstract binding trees (ABT [3]); the text is homoiconic and concatenative.

## Get started

These entry points are planned, not yet published.

### Try it

```sh
nix run github:fpl-org/fpl   # try FPL without cloning
```

### In a container

```sh
podman run -it ghcr.io/fpl-org/fpl
```

### Hack on it

```sh
git clone https://github.com/fpl-org/fpl && cd fpl
direnv allow       # once; without direnv, run `nix develop` each time you enter
nix flake check    # run every gate
```

## Where things are

<pre>
FPL
├── <a href=".agents/">.agents/</a>      # how agents work here (commits, branches, quality)
├── <a href="bootstrap/README.md">bootstrap/</a>    # our first implementation: a Python walker using Lark
├── <a href="docs/">docs/</a>         # design, spec and roadmap
├── <a href="fpl/">fpl/</a>          # FPL's own tree
│   └── <a href="fpl/features/">features/</a> # the executable spec: what FPL must do (spec.md + examples)
├── <a href="quality/">quality/</a>      # the bar every change must clear
├── <a href="scripts/">scripts/</a>      # gates and helpers (land, boundary, commit-lint)
├── <a href="tools/">tools/</a>        # side tools; tokview shows how a tokenizer cuts FPL source
├── <a href="worktrees/">worktrees/</a>    # yours to create: put your worktrees here to hack around
├── <a href="AGENTS.md">AGENTS.md</a>     # start here if you are an agent (or want to work like one)
├── <a href="Makefile">Makefile</a>      # `make check` runs the one gate
└── <a href="flake.nix">flake.nix</a>     # the dev shell: every entry point
</pre>

## References

1. Annenkov, Capriotti, Kraus, Sattler, [*Two-level type theory and applications*](https://doi.org/10.1017/S0960129523000130) (MSCS, 2023), [open copy](https://arxiv.org/abs/1705.03307); Kovács, [*Staged compilation with two-level type theory*](https://doi.org/10.1145/3547641) (ICFP 2022), [open copy](https://arxiv.org/abs/2209.09729).
2. Levy, [*Call-by-Push-Value*](https://doi.org/10.1007/978-94-007-0954-6) (Springer, 2003), [open copy (PhD thesis)](https://www.cs.bham.ac.uk/~pbl/papers/thesisqmwphd.pdf).
3. Harper, [*Practical Foundations for Programming Languages*](https://doi.org/10.1017/CBO9781316576892) (2nd ed., Cambridge, 2016), ch. 1, [open copy (abbreviated edition)](https://www.cs.cmu.edu/~rwh/pfpl/abbrev.pdf).

## Try it in Marimo

```python {.marimo name="try"}
fpl.run.default.file("fpl/features/draft2/examples/01-frames.fpl")
```

```python {.marimo name="try-src"}
fpl.run.default.src("""
double : n -- n
    dup +

2 double
""")
```

```python {.marimo}
fpl.run.default.src("""
4 double
""")
```