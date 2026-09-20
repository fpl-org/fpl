# 2026-09-20 — the project that mediates the language

A note on one choice that has to be made before it can be made well, kept here so it is not
made by accident.

## The pattern

Languages that work tend to have had a project that mediated them while they were being
built. C had Unix. Rust had a browser engine at Mozilla. Go had Google's server
infrastructure. Erlang had Ericsson's telephone switches. Smalltalk had the working
environment it was written to run: an editor, windows, a live image you could open while it
ran.

The instructive case is the one without a single outside project. Haskell's mediator ended up
being its own compiler, and it shows: it is superb at compilers and somewhat awkward
everywhere else.

## What the mediator actually does

Not requirements. Tilt.

The mediating project decides what the language ends up being *good* at, and that never
washes out. C is good at what an operating system needs — bytes, addresses, a thin layer over
the machine — and its weaknesses are the same fact seen from the other side. Go is good at
what a large server fleet needs, and correspondingly blunt where that was not the question.
Erlang is good at what a switch needs, isolation and hot upgrade and failing fast, and strange
outside it.

So choosing the mediating project is choosing a permanent bias. It is not a scheduling
decision and it cannot be revisited later by refactoring, because the bias does not live in a
module. It lives in what the language makes cheap.

## Why that matters here in particular

This repository's ambition is a language that is also an environment, in the line of
Smalltalk, the Lisp machines and Forth. If that is the target, the mediating project has to
exercise the environment and not the compiler.

A version control system, which is otherwise a tempting first thing to self-host, exercises
almost the wrong half: it is I/O and data structures with very little computation, so it
would tilt the language toward content-addressed storage and plumbing and tell us nothing
about the parts a live environment needs. An editor, a shell, a window onto the running
system — those are what shaped Smalltalk, and they ask the questions this project is
eventually about.

## And if there is no outside project at all

The maximal position is to build all of it: language, compiler, environment, tools, the
version control underneath — a refusal of what is not invented here, applied to itself. That
is not a new idea and it is not obviously a mistake. Oberon did it. Forth did it, often down
to the metal. Plan 9 did it. Smalltalk and the Lisp machines did it. TempleOS did it alone.

What the survivors have in common is that they bought totality with one unifying mechanism
and a great deal of cutting. Wirth's rule for Oberon was that the whole system had to be
comprehensible by one person, and everything that did not fit was removed. Plan 9 made
everything a file. Smalltalk sent messages and did nothing else. Forth's answer was to make
the language almost nothing at all. What died are the projects that wanted totality *and*
richness. The hazard is not the scale; it is the number of distinct mechanisms.

The second cost is the one this note began with. Build everything, and there is no mediating
project outside the language: the system mediates itself. That is the Haskell situation
carried to its limit — a closed loop which can be perfectly consistent with its own demands
while saying nothing about whether it is good for anything else. TempleOS is the monument to
that, and it is a monument rather than a tool for exactly this reason.

The move the tradition found against it is small: keep one user outside the loop, using the
thing for something the system itself does not need. Unix had real users. Smalltalk had
children and a research group who wanted things the implementors did not. One is enough.

## Method, and one principle with a precedent

The intended method is conceptual plundering in the manner of Deleuze and Guattari:
take the tradition apart, recombine it, put the pieces down somewhere they did not come from,
and then see what actually works together and what only looked like it would. Hauntology is
the register — the material is a history of computing that did not happen, handled as
something to work with rather than to restore.

The working principle is *sustained velocity*: the project has to accelerate itself, by
bootstrapping and dogfooding, so that the thing being built keeps making the building
cheaper.

That principle has a name and a precedent inside the very tradition being invoked. Engelbart
called it bootstrapping and gave it three levels: A is the work itself, B is improving how
the work is done, and C is improving how the improving is done. Running all three at once is
the method, and it is how his lab built NLS and the mouse — with the tools they were building,
while they were building them. The aim here is the same aim: raise what one ordinary person
can do.

## The tension this leaves

Those two conclusions pull against each other, and both are in the plan.

Sustained velocity says to spend effort on the system making itself better at making itself.
Keeping a user outside the loop says that effort spent inside the loop tells you nothing about
whether any of it is worth having. Every hour that goes into the bootstrap is an hour not
spent on the one outsider who would answer that.

Neither should quietly win by default. Writing both down is how that gets noticed.

## What this does not license

Nothing yet. `docs/DESIGN.md` has no content and there is no grammar, and a mediating project
is meaningless before there is a language to mediate. The order is: settle on a grammar
first; the rest of this note is what to weigh once something runs.

It is written down now only because the choice is easy to make inattentively — by picking up
whatever is convenient to build next — and it is exactly the kind of decision this project
has said it does not want to be haunted by.
