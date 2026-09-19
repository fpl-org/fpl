# TASKS.md — the task graph lives in the repository

Tasks, their order and who is on them are kept as [Radicle](https://radicle.xyz)
collaborative objects (COBs) inside the repository, not as issues on a forge and not as a
file in the tree. A file in the tree would need a pull request for every change of state
(`docs/WORKFLOW.md`, rule 6); issues on a forge leave the record with the forge (rule 7). A
COB is a graph of signed operations under `refs/cobs/<type>/<id>`: it travels with the
repository, and who opened, moved or blocked a task is part of the record, per actor key.

**Status: tooling only.** Nothing uses it until the repository has been through `rad init`,
which creates the maintainer's key and is his step. Needs `rad`: `scripts/layer on radicle`.

```
scripts/task new "parser: integer expressions" -b <id>    # -b: blocked by; repeatable
scripts/task ready                                       # what can be picked up now
scripts/task list [--all]
scripts/task start|done|drop|reopen <id>
scripts/task block|unblock <id> <by>
scripts/task assign <id> <did>|me|nobody
scripts/task edit <id> [-t <title>] [-d <description>]
scripts/task show <id>                                   # the full state, as JSON
```

An `<id>` is any unambiguous prefix. A task is `todo`, `doing`, `done` or `dropped`. It is
*ready* when it is open and every task in its `blockedBy` is done or dropped; a blocker this
clone does not know counts as open.

## Who may do what

An external COB has no authorisation but what its reducer gives it, and any peer can write
operations. So `scripts/rad-cob-task` decides, per operation, by the key that signed it:

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
state out, as JSON (`radicle::cob::external`). The type is `nl.psjg.fpl.task`, so the helper
is `rad-cob-task`; `scripts/task` puts `scripts/` on `PATH` for the `rad` it runs. With plain
`rad cob …` do the same: `PATH="$PWD/scripts:$PATH" rad cob show …`.

Two properties of that protocol shape the helper (checked with `rad` 1.10.3):

- `rad` replays every operation through the helper each time it reads an object. The helper
  is therefore the meaning of the stored operations. Changing it reinterprets every task
  ever written: treat a change to `scripts/rad-cob-task` like a schema migration.
- A helper that exits non-zero makes the object unreadable, for everyone. So it never fails:
  whatever is malformed, unknown or not allowed is skipped and counted. It is also
  deterministic: no clock, no environment, nothing but stdin and stdout.

## What was verified

- `scripts/rad-cob-task --self-test`: the reducer alone, no `rad` needed. Order of `open`,
  the three kinds of actor, junk and oversized input, and that nothing raises.
- `scripts/task --self-test`: every command against a real `rad` in a throwaway home.
- Two `radicle-node`s on an isolated test network on one x86_64-linux machine, two keys:
  the task refs arrive with `rad clone`, helper or no helper; without the helper
  `rad cob show` fails with "failed to spawn program 'rad-cob-task'" and nothing else breaks;
  a stranger's `done` replicates to the author and changes nothing but `ignored`; after
  `assign`, the assignee's `done` replicates and the blocked task turns up in `ready`.

Not verified: macOS; what two operations that are concurrent in the graph resolve to
(`rad` orders them, this was not probed); more than two peers.

## Open decisions

- **The type name.** `nl.psjg.fpl.task` is a placeholder: the convention is a reversed
  domain its owner controls. Renaming it later orphans every task written under the old name,
  so settle it before the first real task.
- Whether repository delegates should be able to act on any task.
