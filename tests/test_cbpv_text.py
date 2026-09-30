"""The printer: Levy's notation, injective on structure."""

from cbpv_strategies import shapes
from hypothesis import given

from fpl.cbpv.syntax import (
    Arrow,
    Base,
    Const,
    F,
    Label,
    LabelKey,
    Lam,
    Node,
    Program,
    Rec,
    Return,
    Var,
)
from fpl.cbpv.text import print as text

INT = Base("Int")


@given(shapes(), shapes())
def test_print_injective(a: Node, b: Node) -> None:
    """[law: print-injective] Two structurally different nodes `shapes()` draws print to
    different text."""
    if a != b:
        assert text(a) != text(b)


def test_one_binder_per_line() -> None:
    body = Label(LabelKey("w", 0), Lam("n", INT, 1, Return(Var("n"))))
    rec = Rec("f", "ω", Arrow(INT, F(INT)), frozenset({"div"}), body)
    assert text(rec).splitlines() == [
        "rec f :ω U{div} (Int → (F Int)).",
        "(label &'w'#0.",
        "(λn :1 Int.",
        "(return n)))",
    ]


def test_program_lists_defs_then_runs() -> None:
    program = Program((("k", Const(3, INT)),), (Return(Var("k")),))
    assert text(program) == "k = (3 : Int)\nrun (return k)"
