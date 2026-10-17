---
type: Pass
title: Source
description: Bytes in, FON out. Not a compiler pass.
tags:
  - boundary
engine: marimo
---

# Source

The pipe does not start on FON. This is the ingress.

```python {.marimo name="source"}
import sys

from fpl.pipe import cli, fonify_text


def main() -> None:
    sys.exit(cli("source"))


if __name__ == "__main__":
    main()
```

