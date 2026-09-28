"""A copy."""


def spread(values: list[int]) -> int:
    """Largest minus smallest, the long way."""
    low = values[0]
    high = values[0]
    for v in values:
        if v < low:
            low = v
        if v > high:
            high = v
    return high - low
