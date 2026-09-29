"""Hypothesis strategies for fpl.asm.wasm: the numbers and modules the properties draw."""

from dataclasses import dataclass
from typing import get_args

from hypothesis import strategies as st

from fpl.asm.wasm.instr import Binop, Const, IBinop, Return
from fpl.asm.wasm.module import Export, Func, Module
from fpl.asm.wasm.types import WIDTH, FuncType, NumType

numtypes = st.sampled_from(get_args(NumType))
valtypes = st.lists(numtypes, max_size=3).map(tuple)


def operands(t: NumType) -> st.SearchStrategy[int]:
    """Values of type t, biased to 0, 1, -1, the signed extremes and shift counts at N."""
    n = WIDTH[t]
    edges = [0, 1, 2**n - 1, 2 ** (n - 1), 2 ** (n - 1) - 1, n, n + 1]
    return st.sampled_from(edges) | st.integers(min_value=0, max_value=2**n - 1)


@dataclass(frozen=True)
class BinopMain:
    """An exported function returning `a op b` in type t; its params and locals go unused."""

    type: NumType
    op: IBinop
    a: int
    b: int
    params: tuple[NumType, ...] = ()
    locals: tuple[NumType, ...] = ()
    name: str = "main"

    def module(self) -> Module:
        """The module holding just that function and its export."""
        t = self.type
        body = (Const(t, self.a), Const(t, self.b), Binop(t, self.op), Return())
        return Module(
            types=(FuncType(self.params, (t,)),),
            funcs=(Func(0, self.locals, body),),
            exports=(Export(self.name, "func", 0),),
        )


@st.composite
def binop_mains(draw: st.DrawFn, *, unused: bool = False) -> BinopMain:
    """A BinopMain; with `unused`, also drawn params, locals and export name."""
    t = draw(numtypes)
    op = draw(st.sampled_from(get_args(IBinop)))
    case = BinopMain(t, op, draw(operands(t)), draw(operands(t)))
    if not unused:
        return case
    return BinopMain(t, op, case.a, case.b, draw(valtypes), draw(valtypes), draw(st.text()))
