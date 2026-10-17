---
type: Composition
title: Build
description: The release chain, a program that orders passes.
tags:
  - composition
engine: marimo
---

# Build

```
build = lex >> parse >> resolve >> expand >> elaborate >> lower >> optimize >> codegen
```

A `>>` chain orders passes. It is not the semantics.

