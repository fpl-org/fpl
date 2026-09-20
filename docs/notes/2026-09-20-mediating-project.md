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

## What this does not license

Nothing yet. `docs/DESIGN.md` has no content and there is no grammar, and a mediating project
is meaningless before there is a language to mediate. The order is: settle on a grammar
first; the rest of this note is what to weigh once something runs.

It is written down now only because the choice is easy to make inattentively — by picking up
whatever is convenient to build next — and it is exactly the kind of decision this project
has said it does not want to be haunted by.
