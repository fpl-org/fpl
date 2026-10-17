---
type: Lab
title: Pipeline
description: The in-process chain beside the shell pipe.
tags:
  - lab
engine: marimo
---

# Pipeline

One cell is the in-process chain. The other is the same passes across FON.

```python {.marimo name="run"}
import fpl

run_now = fpl.lex >> fpl.parse >> fpl.desugar >> fpl.elaborate >> fpl.evaluate
run_now
```
