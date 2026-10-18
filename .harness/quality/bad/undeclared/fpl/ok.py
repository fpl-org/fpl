"""Uses a package it never declared."""

import lark


def double(n: int) -> int:
    """Twice n."""
    return 2 * n


PARSER = lark.Lark
