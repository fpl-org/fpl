---
type: Composition
title: Run
description: The walker's prefix, in-process.
tags:
  - composition
engine: marimo
---

# Run

```
run = lex >> parse >> resolve >> expand >> elaborate >> lower >> evaluate
```

The executable chain is the prefix the walker actually runs. `desugar` stands in for resolve, expand, and lower.

```python {.marimo name="run"}
from fpl.ast_core import Run
from fpl.desugar import desugar, listing
from fpl.elaborate import elaborate
from fpl.errors import FplError
from fpl.evaluate import evaluate
from fpl.lex import lex
from fpl.parse import parse
from fpl.print import render

run_now = lex >> parse >> desugar >> elaborate >> evaluate


def run_file(file: str) -> int:
    """Run one file the way the seed walker does. Goals go to stderr."""
    source = open(file, encoding="utf-8").read()
    try:
        text = render(listing(run_now(source)))
    except FplError as error:
        print(error)
        return 1
    print(text, end="")
    return 0
```

