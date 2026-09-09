# DESIGN.md — the FPL vision

> **Status: TEMPLATE.** This is drawn out with the maintainer in a dedicated interview
> (`.claude/commands/design-fpl.md` / `/design-fpl`). Until the sections below hold real
> content, **agents must not invent language semantics** — build only what a `features/<name>/spec.md`
> authored by the maintainer asks for.
>
> This file is edit-protected: changing it requires the literal `[spec]` marker in the commit
> message (`.githooks/commit-msg`, `.claude/hooks/guard-specs.sh`).

## 1. One sentence

*What is FPL, in a sentence the maintainer would say to another programmer?*

TBD

## 2. Why it exists

*The itch. What existing languages get wrong or make hard, that FPL is a reaction to.*

TBD

## 3. Feel

*A paragraph of prose, then a short program that captures the intended feel — even if nothing
runs it yet.*

TBD

## 4. Non-goals

*What FPL is deliberately not. The features it will decline. The audiences it won't chase.*

TBD

## 5. Influences

*Languages, papers, tools — what to borrow from each, and what to leave.*

TBD

## 6. Core shape (feeds the stable core AST)

*Values, evaluation model (eager/lazy), typing discipline, effects, error model, module model.
This is the part `docs/CONVENTIONS.md`'s `ast_core.py` must stay faithful to.*

TBD

## 7. Open questions

*Things genuinely undecided, with the options on the table.*

TBD

---

Once §§1–6 are real, promote the settled semantics into `docs/SPEC.md` (grammar, evaluation,
type system) and keep this file as the "why".
