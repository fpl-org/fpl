"""Write the Quarto homepage from the checkout README.

The README stays a Marimo notebook. Quarto does not run a ``{.marimo}`` fence,
so this writes ``index.qmd`` with those fences rewritten to ``{python}``. The
setup cell only imports ``fpl`` and is hidden. A cell that raises stays on the
page. ``index.qmd`` is generated.
"""

from __future__ import annotations

import re
from pathlib import Path

_FRONT = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
_FENCE = re.compile(
    r"^```python \{\.marimo([^}]*)\}\n(.*?)^```\n?",
    re.MULTILINE | re.DOTALL,
)

_HEADER = """---
title: FPL
execute:
  enabled: true
  error: true
---
"""


def qmd(readme: str) -> str:
    """Return the Quarto page for one Marimo README."""
    body = _FRONT.sub("", readme, count=1)

    def fence(match: re.Match[str]) -> str:
        attrs = match.group(1)
        code = match.group(2)
        if 'name="setup"' in attrs:
            return "```{python}\n#| echo: false\nimport fpl\n```\n"
        return "```{python}\n" + code + "```\n"

    body = _FENCE.sub(fence, body).lstrip("\n")
    return _HEADER + "\n" + body


def main() -> None:
    """Read the checkout ``README.md`` and write ``index.qmd`` beside it."""
    root = Path(__file__).resolve().parent.parent.parent
    readme = (root / "README.md").read_text(encoding="utf-8")
    (root / "index.qmd").write_text(qmd(readme), encoding="utf-8")


if __name__ == "__main__":
    main()
