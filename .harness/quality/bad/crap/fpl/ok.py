"""Complex, and half of it untested."""


def double(n: int) -> int:
    """Twice n."""
    if n == -1:
        return -2
    if n == -2:
        return -4
    if n == -3:
        return -6
    if n == -4:
        return -8
    if n == -5:
        return -10
    if n == -6:
        return -12
    return 2 * n
