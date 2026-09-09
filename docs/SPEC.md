# SPEC.md — the FPL language specification

> **Status: SKELETON.** Sections fill in as semantics settle — promoted here from
> `docs/DESIGN.md` once decided, and from maintainer-authored `features/<name>/spec.md` as
> features land. This file is the normative reference; `docs/DESIGN.md` holds the *why*.
>
> Edit-protected: changing it requires the `[spec]` marker in the commit message.

## 1. Lexical structure
TBD — defined by `fpl/grammar.lark` terminals once it exists.

## 2. Grammar
TBD — `fpl/grammar.lark` is the source of truth; this section summarises and links it.

## 3. Core language
TBD — the small stable core the surface syntax desugars to (see `docs/CONVENTIONS.md`).

## 4. Evaluation
TBD — evaluation order, values, environment model.

## 5. Type system
TBD — discipline, inference (if any), error model.

## 6. Errors
TBD — every user-facing error is `ERROR: <line>:<col> <message>`; format specified here.
