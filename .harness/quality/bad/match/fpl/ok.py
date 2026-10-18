"""A match with a case missing."""

from enum import Enum


class Sign(Enum):
    """The sign of a number."""

    NEG = -1
    ZERO = 0
    POS = 1


def double(n: int) -> int:
    """Twice n."""
    return 2 * n


def name(sign: Sign) -> str:
    """The sign's name."""
    match sign:
        case Sign.NEG:
            return "negative"
        case Sign.POS:
            return "positive"
