---
type: Pass
title: Render
description: FON in, text out. Not a compiler pass.
tags:
  - boundary
engine: marimo
---

# Render

The pipe ends in text a person can read.

```python {.marimo name="render"}
import sys

from fpl.pipe import cli


def main() -> None:
    sys.exit(cli("render"))


if __name__ == "__main__":
    main()
```

