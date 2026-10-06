# TASKS.md — the task graph lives in the repository

Tasks, their order and who is on them are kept as [Radicle](https://radicle.xyz)
collaborative objects (COBs) inside the repository, not as issues on a forge and not as a
file in the tree. A file in the tree would need a pull request for every change of state
(`.agents/WORKFLOW.md`, rule 6); issues on a forge leave the record with the forge (rule 7). A
COB is a graph of signed operations under `refs/cobs/<type>/<id>`: it travels with the
repository, and who opened, moved or blocked a task is part of the record, per actor key.

**Status: empty.** The repository has been through `rad init`, so the store exists and the
maintainer's key is the one that signs. No task has been written to it. Needs `rad`:
`scripts/layer on radicle`.

```
scripts/task new "parser: integer expressions" -b <id>    # -b: blocked by; repeatable
scripts/task ready                                       # what can be picked up now; 1 on a loop
scripts/task list [--all]
scripts/task start|done|drop|reopen <id>
scripts/task block|unblock <id> <by>                     # block -f records a loop anyway
scripts/task assign <id> <did>|me|nobody
scripts/task edit <id> [-t <title>] [-d <description>]
scripts/task show <id>                                   # the full state, as JSON
```

An `<id>` is any unambiguous prefix. A task is `todo`, `doing`, `done` or `dropped`. It is
*ready* when it is open and every task in its `blockedBy` is done or dropped; a blocker this
clone does not know counts as open.

## Loops

Two tasks that each need the other is a real state of the world — the grammar needs to know
which nodes carry a span, the node set needs to know what the grammar emits — and a record
that cannot say so makes people lie to it. But it is usually a sign that one of the two wants
splitting into the part the other needs, and that is a judgement rather than a rule.

So `block` stops rather than refuses. A block that would close a loop prints the chain and
what it costs, and `block --force` records it anyway:

```
$ scripts/task block 1234567 89abcde
task: that makes a loop: 1234567 -> 89abcde -> 1234567
     nothing in it would be ready. See whether one of them splits into
     the part the other needs; to record the loop anyway, block --force.
```

A loop that arrives anyway — forced, or replicated from a peer who never ran this command
line — may not go quiet. It keeps every task in it out of `ready`, and `ready` then names it
and exits 1:

```
$ scripts/task ready
5ff0a21  todo     lexer: integer literals
# waiting on each other, nothing here can start: 1234567 -> 89abcde -> 1234567
$ echo $?
1
```

The notice goes on stdout rather than stderr, because an agent's harness may drop that stream
or show it only when a command fails, and this is the one thing that must not go unseen. `#`
is the usual skip marker, so `grep -v '^#'` leaves a list of tasks. The exit code answers
rather than complains, the way `git diff --exit-code` does; write `|| true` where the answer
does not matter.

Which leaves stderr for what it is good at. A refusal — an unknown id, a `block` that would
close a loop, no `rad` on the path — goes there and exits **2**. So the three codes divide
the way `grep` divides them:

| | |
|---|---|
| **0** | the answer: here is what can be picked up |
| **1** | an answer with bad news in it: a loop, and nothing in it can start |
| **2** | the command was refused and did nothing |

A harness can act on the code alone, without reading either stream. (`sysexits(3)` was the
other candidate and is not used: FreeBSD's own manual now says the interface "has been
deprecated and is retained only for compatibility", and its codes describe kinds of failure,
which leaves no room for an answer that succeeded and carries bad news.)

A blocker that is not open does not hold anything up and so cannot be part of a loop; neither
can one this clone has not replicated.

Both halves are needed, and neither is a guarantee. The check at `block` is a guard on the
path people take; the report at `ready` catches what comes in past it. Acyclicity cannot be
enforced where the authorisation is: the reducer sees one task at a time, a loop spans
several, and a peer can always write operations without the command line. The graph is
acyclic when it is healthy, and a loop is a diagnosis rather than a forbidden shape.

## Who may do what

An external COB has no authorisation but what its reducer gives it, and any peer can write
operations. So `scripts/rad-cob-dagtaak` decides, per operation, by the key that signed it:

| Actor | May |
| --- | --- |
| the author of the task | everything: edit, assign, state, blockers |
| the assignee | state and blockers |
| anyone else | nothing; the operation stays in the record and is counted in `ignored` |

An agent gets its own Radicle key, is assigned a task, and can then start and finish it; the
record shows that it did. Repository delegates are not consulted.

## How it works

`rad` knows issues and patches. For any other type it runs a helper, named after the last
segment of the type name, once per operation: the state so far and the operation in, the new
state out, as JSON (`radicle::cob::external`). The type is `nl.psjs.dagtaak`, so the helper
is `rad-cob-dagtaak`; `scripts/task` puts `scripts/` on `PATH` for the `rad` it runs. With plain
`rad cob …` do the same: `PATH="$PWD/scripts:$PATH" rad cob show …`.

The name is settled. It is a reversed domain the maintainer owns, and it carries no project:
the graph is meant to outlive this repository, so a task written here reads the same in
whatever comes next. Renaming it again would orphan every task written under the old name,
because `rad` looks the helper up by the last segment and would not find the old refs.

Two properties of that protocol shape the helper (checked with `rad` 1.10.3):

- `rad` replays every operation through the helper each time it reads an object. The helper
  is therefore the meaning of the stored operations. Changing it reinterprets every task
  ever written: treat a change to `scripts/rad-cob-dagtaak` like a schema migration.
- A helper that exits non-zero makes the object unreadable, for everyone. So it never fails:
  whatever is malformed, unknown or not allowed is skipped and counted. It is also
  deterministic: no clock, no environment, nothing but stdin and stdout.

## What was verified

- `scripts/rad-cob-dagtaak --self-test`: the reducer alone, no `rad` needed. Order of `open`,
  the three kinds of actor, junk and oversized input, and that nothing raises.
- `scripts/task --self-test`: every command against a real `rad` in a throwaway home,
  including a two-task loop: the second `block` is refused and says how to go on, `--force`
  records it, both stay out of `ready`, `ready` names them, and dropping one frees the other.
- Two `radicle-node`s on an isolated test network on one x86_64-linux machine, two keys:
  the task refs arrive with `rad clone`, helper or no helper; without the helper
  `rad cob show` fails with "failed to spawn program 'rad-cob-dagtaak'" and nothing else breaks;
  a stranger's `done` replicates to the author and changes nothing but `ignored`; after
  `assign`, the assignee's `done` replicates and the blocked task turns up in `ready`.
- Both self-tests on aarch64-darwin, against the maintainer's own `rad` 1.10.3 in the repository
  initialised above: the same 16 and 18 checks that pass on x86_64-linux.

Not verified: what two operations that are concurrent in the graph resolve to
(`rad` orders them, this was not probed); more than two peers.

## Open decisions

- Whether repository delegates should be able to act on any task.
