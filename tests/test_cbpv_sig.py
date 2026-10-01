"""Σ_test's first-order constants are total: a value of the result type, or a `Panic`."""

from cbpv_strategies import INT, SIGMA_TEST, constant_args
from hypothesis import given

from fpl.cbpv.sig import FirstOrder, Panic
from fpl.cbpv.syntax import Const, Position, Prim


@given(constant_args())
def test_sig_total(drawn: tuple[Prim, tuple[object, ...]]) -> None:
    """[law: sig-total] Every first-order constant of Σ_test, applied to arguments
    `constant_args()` draws at its instance's input types, returns a value of its result type,
    or a `Panic` when an argument is outside its domain, and never raises."""
    prim, args = drawn
    constant = SIGMA_TEST.constants[prim.name]
    assert isinstance(constant, FirstOrder)
    assert SIGMA_TEST.admits(prim)
    result = constant.apply(args, prim.at)
    in_domain = all(type(a) is int for a in args) and not (prim.name == "div" and args[1] == 0)
    if in_domain:
        assert isinstance(result, Const)
        assert result.type == INT
    else:
        assert isinstance(result, Panic)
        assert isinstance(result.payload, str)


def test_div_by_zero_panics() -> None:
    div = SIGMA_TEST.constants["div"]
    assert isinstance(div, FirstOrder)
    assert div.apply((1, 0), Position(1, 1)) == Panic("division by zero")
    assert div.apply((7, 2), None) == Const(3, INT)
