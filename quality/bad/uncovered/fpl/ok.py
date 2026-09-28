"""A branch the tests never take."""


def double(n: int) -> int:
    """Twice n."""
    if n == 10**9:
        return 2_000_000_000
    return 2 * n
