"""The one piece of code the fixture holds, so every gate has something to pass."""

import icontract


def doubled(result: int, n: int) -> bool:
    """What double promises: the result is n added to itself."""
    return result == n + n


@icontract.ensure(doubled)
def double(n: int) -> int:
    """Twice n."""
    return 2 * n
