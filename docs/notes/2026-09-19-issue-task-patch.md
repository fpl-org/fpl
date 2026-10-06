# 2026-09-19 — issue, task, patch

A proposal, not a decision. None of it is implemented. If it is accepted it moves into
`.agents/TASKS.md` and this note goes away; if it is not, the note records why.

## Three objects, and the work each one does

"Issue" carries its meaning from the courtroom rather than from the bug tracker. The legal
sense is the older one — the point put forward to be determined — and it comes from *exire*,
to go out. That is what an issue does: it puts a matter forward. It says nothing about when
the matter is dealt with, or in what order relative to other matters.

| | carries | does not carry |
| --- | --- | --- |
| `xyz.radicle.issue` | the matter, and the discussion about it | order, dependencies |
| `nl.psjs.dagtaak` | order, state, assignee, and a pointer to an issue | discussion |
| `xyz.radicle.patch` | the change, its revisions, the verdicts on them | — |

A task points at an issue. One or more patches are offered against it. A patch that is
accepted and lands satisfies the task; one that is rejected sends it back for another
revision. That loop already lives inside the patch object, per revision and per reviewer, so
the task does not model review and never grows comments of its own. Everything that is
conversation stays in the issue, and the existing tooling — `rad issue`, `rad patch`, the TUI,
the desktop app — keeps working on it unchanged.

This is the whole reason the custom type stays small. It adds the one thing Radicle has no
place for, which is the edge between two pieces of work.

## Why there is no plan object

A plan proposes to add tasks and the edges between them. But a collaborative object *is* an
operation log: every operation is already a delta on the graph, signed by whoever made it. So
a plan is not a new kind of object — it is a bundle of operations that has not been applied
yet. Two things separate such a bundle from a bare operation: the grouping, and the
not-yet-applied state. The first is an edge, described below. The second is what a patch
already is.

The question the idea was reaching for is a different one and is not needed to build any of
this: when are two decompositions of the same work the same plan?

## Two kinds of edge

`blockedBy` is order: this cannot start until that is finished. It is the edge `ready` walks,
and the edge a loop is a loop in.

`partOf` is containment: this is one of the pieces that together make up that. `ready` never
walks it.

Putting both in one relation leaves a graph that still parses but cannot answer either
question. Asking what belongs to a feature returns things that merely precede it; asking what
can start returns containers. A container has no work of its own, so it is never ready, and it
blocks nothing — what blocks is its contents.

A direction — the thing that is not yet a task, "zou het niet cool zijn als" — is then the top
of a `partOf` tree rather than a column on a board. It sits in `list` and never in `ready`,
for the same reason any container does.

## Depth and width, not a calendar

A Gantt chart is three things stacked: dependencies, decomposition, and a time axis from which
start dates, float and the critical path follow. The first two are the two edges above. The
third does not transfer, because a duration estimate for agent work is not a real number: a
task takes four minutes, or it fails, or it costs three rounds of review because the first
attempt solved the wrong problem. A chart drawn from invented durations is not a plan, it is a
picture that then gets planned against.

What survives without a single date is the useful half. The critical path is the longest chain
through the graph, and it can be counted in steps. The width is how many tasks are ready at
once, which is the answer to how many agents can usefully work here before they are waiting on
each other. Both follow from `blockedBy` alone.

Shape Up's hill chart is the same move made earlier: it places each scope on a slope from
unknown to known, with no estimates and no percentages, and reads progress from whether a dot
moves between snapshots rather than from a number.

The time axis can come back afterwards. Every operation is timestamped and signed, so the real
sequence can be drawn once the work is done. That is a record of what happened, not a forecast,
and it is the only honest Gantt here.

## Open

- A direction with no contents yet is a leaf, and by the rule above a leaf is ready. Either
  containers are marked as such, or the `idea` state comes back to do that job.
- Whether a task may point at more than one issue.
- Whether the patches offered against a task are recorded on the task or read from the patches.
