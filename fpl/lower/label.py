"""Pass 3, label: cbpv⁻ to cbpv, a label at the head of every loop (design section 6.4).

Promised: `label` inserts `label l.` at every definition entry (the head of a definition's
thunk, outside its λs), at the head of every `Rec` body (of each component of a `Both` under
it), and at the head of every thunk literal an iterating constant takes (the loop bodies pass 2
wraps); nothing else changes. So the output passes `check(loops=True)` when the input passes
`check(loops=False)` (law labels-per-loop), and it ends as the input does, with the same events
once its labels are removed (law label-pass-preserves): a label step only emits its key.

Keys are `LabelKey(word, ordinal)`: the definition's name, or `line N` for the program's N-th
run (the IR keeps no source line), with ordinals from 0 in the order the pass meets the labels,
outside in and left to right (hole label-keys).
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, fields, replace
from itertools import count
from typing import Any, get_args

from fpl.cbpv.sig import Iterating, Signature
from fpl.cbpv.syntax import App, Both, Comp, Label, LabelKey, Prim, Program, Rec, Thunk, Value

# The classes whose instances the pass walks into: values and computations, not types.
_NODES = (*get_args(Value.__value__), *get_args(Comp.__value__))


@dataclass
class _Labeller:
    """Labels one definition or run: the word its keys name, the ordinals left, and the
    signature that says which constants iterate."""

    word: str
    sig: Signature
    ordinals: Iterator[int] = field(default_factory=count)

    def entered(self, thunk: Thunk) -> Thunk:
        """`thunk` with a label at the head of its body, its origin kept."""
        return replace(thunk, body=self.labelled(thunk.body))

    def labelled(self, m: Comp) -> Label:
        key = LabelKey(self.word, next(self.ordinals))
        return Label(key, self.node(m))

    def leading(self, m: Comp) -> Comp:
        """`m` led by a label: a pair `⟨M₁, M₂⟩` by leading both components."""
        if isinstance(m, Both):
            return Both(self.leading(m.left), self.leading(m.right))
        return self.labelled(m)

    def node(self, x: Value | Comp) -> Any:
        """`x` with its loops labelled: a `Rec` or an application spine by its rule, any other
        node by labelling each child that is a value or a computation."""
        rule = _RULES.get(type(x))
        if rule is not None:
            return rule(self, x)
        children = {f.name: getattr(x, f.name) for f in fields(x)}
        return replace(x, **{k: self.node(v) for k, v in children.items() if isinstance(v, _NODES)})


def _rec(low: _Labeller, m: Rec) -> Rec:
    return replace(m, body=low.leading(m.body))


def _spine(low: _Labeller, m: App) -> Comp:
    """`H` applied to `V₁ … Vₙ`, each thunk literal among the `Vᵢ` entered when `H` is an
    iterating constant (the checker holds only those to the label rule)."""
    args: list[Value] = []
    head: Comp = m
    while isinstance(head, App):
        args.append(head.arg)
        head = head.fun
    loops = isinstance(head, Prim) and isinstance(low.sig.constants.get(head.name), Iterating)
    values = [low.entered(v) if loops and isinstance(v, Thunk) else low.node(v) for v in args]
    comp: Comp = low.node(head)
    for value in reversed(values):
        comp = App(value, comp)
    return comp


_RULES: dict[type, Callable[[_Labeller, Any], Comp]] = {Rec: _rec, App: _spine}


def _defined(name: str, value: Value, sig: Signature) -> Value:
    low = _Labeller(name, sig)
    return low.entered(value) if isinstance(value, Thunk) else low.node(value)


def label(program: Program, sig: Signature) -> Program:
    """`program` with a label at every definition entry, `Rec` body and loop body, under `sig`
    (which says which constants iterate)."""
    defs = tuple((name, _defined(name, value, sig)) for name, value in program.defs)
    runs = tuple(_Labeller(f"line {i}", sig).node(m) for i, m in enumerate(program.runs, 1))
    return Program(defs, runs)
