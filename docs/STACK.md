# STACK.md — the implementation stack, and why

This decision is **settled**. It was reached with the maintainer after consulting two external
advisors (a ChatGPT session and a Fable 5.1 session). Reopen it only with the maintainer, and
only with new information. This document exists so it isn't relitigated in every worktree.

## The decision

> **Python 3.12+ + Lark + frozen `@dataclass` AST nodes + structural `match` → tree-walking
> interpreter**, with a layered frontend and one non-interactive `make check` gate.

## Why Python + Lark

The goal is a workbench where the maintainer changes the language design and an agent makes it
work minutes later. That makes **agent fluency the primary metric** — how much correct code an
agent produces per token — and Python + `pytest` is the densest corpus available. `match` over
`@dataclass` gives near-free AST definitions and evaluators.

[Lark](https://lark-parser.readthedocs.io) suits language *design* specifically: start with
**Earley**, which accepts essentially arbitrary CFGs and can surface ambiguities explicitly,
then move the same grammar toward LALR once the syntax settles. The grammar file doubles as
the human-readable syntax spec.

## Alternatives considered

| Option | Verdict |
| --- | --- |
| **TypeScript + Ohm** | Elegant grammar/semantics separation, browser tooling. Rejected *for agents*: semantics split across two places, and a missing semantic action fails at runtime — a slower, noisier feedback loop than a static `match` exhaustiveness error. |
| **OCaml + Menhir** | The strongest *verifier* stack — exhaustive variants make the AST a checked spec. Rejected: opam/dune friction and a thinner training corpus cost the "minutes later" goal. Revisit if the prototype graduates to a serious compiler. |
| **Racket** | Desugaring for free via macros, great for weird semantics. Rejected: weakest agent fluency of the credible options. |
| **flex + Bison + C** | Appropriate for a settled grammar and a native compiler. Rejected now: every syntax experiment drags lexer, `%union`, allocation, and AST constructors along with it. |
| **LLVM frontend directly** | Much later, if ever. |

## Consequences (these are requirements, not suggestions)

1. **Layered frontend.** source → surface AST → `desugar` → tiny core AST → semantics. All
   sugar is erased in `desugar`; the core AST stays small and stable; the evaluator only ever
   sees core AST. Syntactic experiments become grammar + desugar changes.
2. **Recover the missing compiler.** Python won't catch a mistyped field or a non-exhaustive
   `match`. `pyright` runs in strict mode with `reportMatchNotExhaustive` as an error, over
   **frozen** dataclasses. A pyright error is a build failure.
3. **Ambiguity gate.** Earley silently accepts ambiguous grammars, and the pain surfaces
   months later as "why did precedence change". The grammar loads with `ambiguity='explicit'`
   and a test asserts zero ambiguity over the example corpus.
4. **Don't let the agent be its own oracle.** The maintainer authors `spec.md`, the `.fpl`
   examples, and the `.expected` files. The agent makes `make check` green against them. See
   `CONVENTIONS.md`.
5. **Cheat on the backend.** When compilation matters: core IR → C → `clang`. Clang is the
   optimiser, instruction selector, assembler, and linker. Swapping IR→C for IR→LLVM later
   doesn't touch the frontend.
6. **tree-sitter is editor tooling**, added later, never the semantic frontend. Lark stays the
   frontend; tree-sitter (if added) serves highlighting, incremental parsing, and structural
   editing.

## Open question deferred to `design-fpl`

Whether the grammar file stays hand-edited (keep Lark) or the maintainer stops editing it in
practice (consider hand-written recursive descent for better error messages). Decide once
there's real usage data.
