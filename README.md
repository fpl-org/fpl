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
├── <a href="01-bootstrap/README.md">01-bootstrap/</a>    # our first implementation: a Python walker using Lark
│   ├── <a href="01-bootstrap/01.01-boundary/">01.01-boundary/</a>
│   │   ├── <a href="01-bootstrap/01.01-boundary/01.01.01-source.md">01.01.01-source.md</a>
│   │   ├── <a href="01-bootstrap/01.01-boundary/01.01.02-fon.md">01.01.02-fon.md</a>
│   │   ├── <a href="01-bootstrap/01.01-boundary/01.01.03-pipe.md">01.01.03-pipe.md</a>
│   │   └── <a href="01-bootstrap/01.01-boundary/01.01.04-render.md">01.01.04-render.md</a>
│   ├── <a href="01-bootstrap/01.02-pass/">01.02-pass/</a>
│   │   ├── <a href="01-bootstrap/01.02-pass/01.02.01-lex.md">01.02.01-lex.md</a>
│   │   ├── <a href="01-bootstrap/01.02-pass/01.02.02-parse.md">01.02.02-parse.md</a>
│   │   ├── <a href="01-bootstrap/01.02-pass/01.02.03-resolve.md">01.02.03-resolve.md</a>
│   │   ├── <a href="01-bootstrap/01.02-pass/01.02.04-expand.md">01.02.04-expand.md</a>
│   │   ├── <a href="01-bootstrap/01.02-pass/01.02.05-desugar.md">01.02.05-desugar.md</a>
│   │   ├── <a href="01-bootstrap/01.02-pass/01.02.06-elaborate.md">01.02.06-elaborate.md</a>
│   │   ├── <a href="01-bootstrap/01.02-pass/01.02.07-lower.md">01.02.07-lower.md</a>
│   │   ├── <a href="01-bootstrap/01.02-pass/01.02.08-normalize.md">01.02.08-normalize.md</a>
│   │   ├── <a href="01-bootstrap/01.02-pass/01.02.09-optimize.md">01.02.09-optimize.md</a>
│   │   ├── <a href="01-bootstrap/01.02-pass/01.02.10-evaluate.md">01.02.10-evaluate.md</a>
│   │   └── <a href="01-bootstrap/01.02-pass/01.02.11-codegen.md">01.02.11-codegen.md</a>
│   ├── <a href="01-bootstrap/01.03-repr/">01.03-repr/</a>
│   │   ├── <a href="01-bootstrap/01.03-repr/01.03.01-source.md">01.03.01-source.md</a>
│   │   ├── <a href="01-bootstrap/01.03-repr/01.03.02-tokens.md">01.03.02-tokens.md</a>
│   │   ├── <a href="01-bootstrap/01.03-repr/01.03.03-syntax.md">01.03.03-syntax.md</a>
│   │   ├── <a href="01-bootstrap/01.03-repr/01.03.04-resolved.md">01.03.04-resolved.md</a>
│   │   ├── <a href="01-bootstrap/01.03-repr/01.03.05-expanded.md">01.03.05-expanded.md</a>
│   │   ├── <a href="01-bootstrap/01.03-repr/01.03.06-elaborated.md">01.03.06-elaborated.md</a>
│   │   └── <a href="01-bootstrap/01.03-repr/01.03.07-core.md">01.03.07-core.md</a>
│   ├── <a href="01-bootstrap/01.04-compose/">01.04-compose/</a>
│   │   ├── <a href="01-bootstrap/01.04-compose/01.04.01-pass.md">01.04.01-pass.md</a>
│   │   ├── <a href="01-bootstrap/01.04-compose/01.04.02-run.md">01.04.02-run.md</a>
│   │   ├── <a href="01-bootstrap/01.04-compose/01.04.03-inspect.md">01.04.03-inspect.md</a>
│   │   └── <a href="01-bootstrap/01.04-compose/01.04.04-build.md">01.04.04-build.md</a>
│   ├── <a href="01-bootstrap/01.05-labs/">01.05-labs/</a>
│   │   └── <a href="01-bootstrap/01.05-labs/01.05.01-pipeline.md">01.05.01-pipeline.md</a>
│   └── <a href="01-bootstrap/01.06-nagini/">01.06-nagini/</a>
│       └── <a href="01-bootstrap/01.06-nagini/01.06.01-advance.md">01.06.01-advance.md</a>
├── <a href="02-docs/">02-docs/</a>         # design, spec and roadmap
│   ├── <a href="02-docs/02.01-design.md">02.01-design.md</a>
│   ├── <a href="02-docs/02.02-spec.md">02.02-spec.md</a>
│   ├── <a href="02-docs/02.03-roadmap.md">02.03-roadmap.md</a>
│   └── <a href="02-docs/02.04-notes/">02.04-notes/</a>
│       ├── <a href="02-docs/02.04-notes/02.04.01-issue-task-patch.md">02.04.01-issue-task-patch.md</a>
│       ├── <a href="02-docs/02.04-notes/02.04.02-sober.md">02.04.02-sober.md</a>
│       └── <a href="02-docs/02.04-notes/02.04.03-mediating-project.md">02.04.03-mediating-project.md</a>
├── <a href="03-fpl/">03-fpl/</a>          # FPL's own tree
│   └── <a href="03-fpl/03.01-features/">03.01-features/</a> # the executable spec: what FPL must do (spec.md + examples)
├── <a href=".harness/quality/">.harness/quality/</a>      # the bar every change must clear
├── <a href=".harness/scripts/">.harness/scripts/</a>      # gates and helpers (land, boundary, commit-lint)
├── <a href=".harness/tools/">.harness/tools/</a>        # side tools; tokview shows how a tokenizer cuts FPL source
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
fpl.run.default.file("03-fpl/03.01-features/draft2/examples/01-frames.fpl")
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