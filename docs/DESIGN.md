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

### Which accelerator, and can they be one mechanism

The stated working principle is that the project should accelerate itself
(`docs/notes/2026-09-20-mediating-project.md`). Three candidate accelerators are on the table.
Each is real, each has a cost, and every one of those costs lands on the same principle.

**Liveness.** A live image shortens the loop between changing something and seeing it to
almost nothing, which is probably the largest single factor early on. Smalltalk and Factor are
the precedents. The cost is reproducibility: an image accumulates state that cannot be
reconstructed from source, which runs against a record that travels with the repository
(`docs/TASKS.md`, `docs/WORKFLOW.md` rule 7).

**Brevity.** Two different things get called this and they should not be confused. Semantic
brevity is implicit iteration and a small set of very general combinators — APL, J and K do not
write loops because their primitives work over whole arrays. Typographic brevity is
single-glyph names, which saves typing, and typing is not the bottleneck. Golfing languages
such as Vyxal sit at the far end and optimise for bytes in a one-shot solution. The cost is
that concatenative and tacit code is hard to read back, including by its author, and velocity
over months is mostly a re-reading problem.

**Correctness by construction.** Refinement types and type-driven development slow the first
week and are meant to hold the pace as a codebase grows. Combining refinement-strength types
with gradual typing is an existing line of work rather than a wish: Lehmann and Tanter,
*Gradual Refinement Types*, POPL 2017; Vazou and others, *Gradual Liquid Type Inference*. The
cost is measured and it is not small. Takikawa and others (*Is Sound Gradual Typing Dead?*,
POPL 2016) ran twelve programs in every combination of typed and untyped modules and found
that typing a single module could cost 88x, with other implementations at 10x (Reticulated
Python) and 22x (Safe TypeScript); under a 3x threshold almost no partial configuration was
deployable. That is why unsound erasure won in practice. The result is contested and has
improved since — the follow-ups are titled "only mostly dead", "nominally alive and well" and
"Corpse reviver" — so this is a live front rather than a closed door. The cost sits at the
boundary between typed and untyped code, so the boundary discipline is the thing to design,
not the type system.

The question is not which one to pick. It is whether they can be a single mechanism, because
a system that is total *and* many-mechanismed is the shape that historically dies.

### Which extension mechanism

Related and prior to the above. Forth, Lisp and Smalltalk give three different answers to "how
does a user extend the language": the compiler as a library (`CREATE … DOES>`, immediate
words, a dictionary that is open at runtime), code as data, and objects in a live image.
Taking all three means three mechanisms.

Factor is the existence proof that some of this composes: it is concatenative, has an object
system of tuple classes as a central part, a Smalltalk-style image, a self-hosted optimising
compiler and an interactive environment, and it got there by making concatenation the one
mechanism and growing the object system out of the language rather than beside it. Object
systems on Forth are likewise small enough to fit in a few pages (Gforth's Mini-OOF; Pountain,
*Object-Oriented Forth*, 1987). Nothing here shows that the third accelerator joins them.

---

Once §§1–6 are real, promote the settled semantics into `docs/SPEC.md` (grammar, evaluation,
type system) and keep this file as the "why".
