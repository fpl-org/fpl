"""The model: register names by width (C6.1.3: register 31 is sp or the zero register)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fpl.asm.aarch64.model import Reg, Width

# fmt: off
NAMES = [
    (Reg.X0, "x0"), (Reg.X1, "x1"), (Reg.X2, "x2"), (Reg.X3, "x3"), (Reg.X4, "x4"),
    (Reg.X5, "x5"), (Reg.X6, "x6"), (Reg.X7, "x7"), (Reg.X8, "x8"), (Reg.X9, "x9"),
    (Reg.X10, "x10"), (Reg.X11, "x11"), (Reg.X12, "x12"), (Reg.X13, "x13"), (Reg.X14, "x14"),
    (Reg.X15, "x15"), (Reg.X16, "x16"), (Reg.X17, "x17"), (Reg.X18, "x18"), (Reg.X19, "x19"),
    (Reg.X20, "x20"), (Reg.X21, "x21"), (Reg.X22, "x22"), (Reg.X23, "x23"), (Reg.X24, "x24"),
    (Reg.X25, "x25"), (Reg.X26, "x26"), (Reg.X27, "x27"), (Reg.X28, "x28"), (Reg.X29, "x29"),
    (Reg.X30, "x30"), (Reg.SP, "sp"), (Reg.ZR, "xzr"),
]
# fmt: on


def test_every_register_is_named() -> None:
    assert sorted(reg for reg, _ in NAMES) == list(Reg)


@pytest.mark.parametrize(("reg", "name"), NAMES)
def test_the_x_names(reg: Reg, name: str) -> None:
    assert reg.name_at(Width.W64) == name


@given(st.sampled_from(Reg))
def test_a_w_name_is_its_x_name_with_w(reg: Reg) -> None:
    """The 32-bit view renames x to w, sp to wsp and xzr to wzr."""
    x = reg.name_at(Width.W64)
    assert reg.name_at(Width.W32) == ("wsp" if x == "sp" else "w" + x[1:])
