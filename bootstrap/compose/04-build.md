---
type: Composition
title: Build
description: The release chain, a program that orders passes.
tags:
  - composition
engine: marimo
marimo-version: 0.23.10
width: full
---

```python {.marimo name="setup"}
import marimo as mo
```

# Build

```
build = lex >> parse >> resolve >> expand >> elaborate >> lower >> optimize >> codegen
```

A `>>` chain orders passes. It is not the semantics.

