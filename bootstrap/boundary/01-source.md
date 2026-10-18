---
type: Pass
title: Source
description: Bytes in, FON out. Not a compiler pass.
tags:
  - boundary
engine: marimo
marimo-version: 0.23.10
width: full
---

```python {.marimo name="setup"}
import marimo as mo
```

# Source

The pipe does not start on FON. This is the ingress.

```python {.marimo name="source"}
import sys

from fpl.pipe import cli


def main() -> None:
    sys.exit(cli("source"))


if __name__ == "__main__":
    main()
```

