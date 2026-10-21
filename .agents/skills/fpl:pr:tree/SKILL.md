---
name: fpl:pr:tree
description: Draw the open pull requests as the tree their bases make, with scripts/stack-tree. Use to see which pull request lands first, what is stacked on what, and which one needs retargeting; it reads the forge and writes nothing.
---

    scripts/stack-tree [--repo <owner>/<name>]

GitHub lists pull requests flat; this prints them as the tree of their bases. The roots, based
on `main`, are what `fpl:land` takes, bottom first; a child of a landed branch is retargeted
to `main` (the lander prints the command). A tree it cannot draw whole, a base that is no
open pull request, is refused rather than drawn in part. It stays in `scripts/` while pull
request 198 on it is open.

- **Exit 0**: the tree on stdout. **Exit 1**: the forge could not be read, or the list is not
  one tree; the message names the pull request.
