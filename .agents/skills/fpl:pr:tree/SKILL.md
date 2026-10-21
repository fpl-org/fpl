---
name: fpl:pr:tree
description: Draw the open pull requests as the tree their bases make, with scripts/stack-tree. Use to see which pull request lands first, what is stacked on what, and which one needs retargeting; it reads the forge and writes nothing.
---

    scripts/stack-tree [--repo <owner>/<name>] [--json <file>]

GitHub lists pull requests flat; this prints them as the trees their bases make. The roots
based on `main` are what `fpl:land` takes, bottom first. A pull request whose base is neither
`main` nor an open pull request (its parent landed or closed) is drawn as a root too,
annotated: it needs a retarget to `main` first (the lander prints the command). It stays in
`scripts/` while pull request 198 on it is open.

- **Exit 0**: the trees on stdout (nothing open draws that). **Exit 2**: a refusal, with its
  rule and remedy: the forge could not be read, two pull requests share a head branch, a
  cycle, 300 open (some may be missing), or a bad command line. Exit 1 is the self-test's.
