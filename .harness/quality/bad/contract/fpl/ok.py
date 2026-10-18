"""A postcondition that holds for most inputs, but not for 0 or below."""

import icontract


def grows(result: int, n: int) -> bool:
    """A promise double cannot keep for n <= 0."""
    return result > n


@icontract.ensure(grows)
def double(n: int) -> int:
    """Twice n."""
    return 2 * n
