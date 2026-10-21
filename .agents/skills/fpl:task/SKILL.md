---
name: fpl:task
description: Work the task graph kept in the repository as Radicle collaborative objects, with .agents/skills/fpl:task/scripts/task. Use when picking up, opening, blocking, finishing or inspecting a unit of work, or when asked what is ready or how the units relate.
---

Tasks live under `refs/cobs/nl.psjs.dagtaak/` of the Radicle repository, signed per actor;
needs `rad` (`layer on radicle`) and a clone that went through `rad init`. The model
(ready, lanes, loops, who may do what): `.agents/TASKS.md`. The routine:

1. **What can be picked up**: `fpl:task:ready`. The whole tree, with what waits on what:
   `fpl:task:tree`.
2. **Open work**, one task per unit, blocked by what must land first, part of its lane:

       T=.agents/skills/fpl:task/scripts/task
       $T new "<title>" [-d <description>] [-b <id>]... [-p <lane>]
       $T start|done|drop|reopen <id>
       $T block [-f] <id> <by>  |  unblock <id> <by>  |  part <id> <of>|none
       $T assign <id> <did>|me|nobody  |  edit <id> [-t <title>] [-d <description>]
       $T list [--all]  |  show <id>

   A units file instead of one `new` per task: `fpl:task:load`.
3. An `<id>` is the first word of a title (`A6a`) or an unambiguous prefix of the object id.

Exit codes, grep's way: **0** the answer; **1** the answer carries bad news, named on stdout
after `#`: a loop that keeps tasks out of `ready`, or a part `tree` cannot draw; **2** refused
or failed, the reason on stderr (unknown id, a `block` that would close a loop: split one task
or `block -f`). A refusal comes before any write. A `rad` that fails, or a write the reducer
skips, can come after one, and `load` writes row by row: read the state (`list`, `show`)
before a rerun.

`rad` finds the reducer `scripts/rad-cob-dagtaak` on `PATH`, where `task` puts the root's
`scripts/`; with plain `rad cob` do the same: `PATH="$PWD/scripts:$PATH" rad cob show …`. The
reducer stays in `scripts/`: `PATH` splits on colons and this skill's directory holds one.
Both have `--self-test`; `make gates` runs them through their header lines (task needs nix).
