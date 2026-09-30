"""The execution of WebAssembly, spec 4.6-4.7, for the subset of `fpl.asm.wasm`.

`instantiate` builds the instance of a closed module (4.7.2): no imports, no start function,
so "modelled, printed and checked, not run" holds for both. `invoke` runs one of its functions
(4.7.3) big-step over the instruction tree and ends in an `Outcome`, never an exception.

Costs and limits, both the evaluator's own and never compared with an engine: every instruction
executed costs one step, charged before it runs, and nothing else costs one; a run that needs a
step past its budget is `OutOfSteps`. At most `DEPTH` calls are active at once; a call past them
is `Exhausted` (spec 7.3.3 leaves the limit to the implementation; HOLES.md exhaustion-outcome).
A tail call replaces its caller's frame in the call driver's loop, so it never deepens either
the call depth or the Python stack.

A trap stops the run without rollback: globals and memory keep what the run wrote before it, as
the engines keep them. Branches, returns and tail calls travel as Python exceptions that never
leave `invoke`.
"""

from collections.abc import Callable, MutableSequence, Sequence
from dataclasses import dataclass
from typing import Any, assert_never

from fpl.asm.wasm.instr import (
    Binop,
    Block,
    Br,
    BrIf,
    BrTable,
    Call,
    CallIndirect,
    Const,
    Cvtop,
    Drop,
    GlobalGet,
    GlobalSet,
    If,
    Instr,
    Load,
    LocalGet,
    LocalSet,
    LocalTee,
    Loop,
    MemArg,
    MemorySize,
    Nop,
    Relop,
    Return,
    ReturnCall,
    ReturnCallIndirect,
    Select,
    Store,
    Testop,
    Unop,
    Unreachable,
)
from fpl.asm.wasm.module import Expr, Module
from fpl.asm.wasm.numerics import BINOPS, CVTOPS, RELOPS, TESTOPS, UNOPS, Trap, TrapKind, signed
from fpl.asm.wasm.types import WIDTH, BlockType, FuncType, TypeUse

PAGE = 1 << 16
"""The page size of a memory in bytes (2.3.15)."""

DEPTH = 64
"""The most calls active at once; with at most two Python frames per label and three per call,
the run stays far below Python's own recursion limit."""


@dataclass(frozen=True, slots=True)
class Values:
    """The run returned these results, each unsigned (4.3.1)."""

    values: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class OutOfSteps:
    """The run needed a step past its budget."""


@dataclass(frozen=True, slots=True)
class Exhausted:
    """The run called past `DEPTH` active calls."""


Outcome = Values | Trap | OutOfSteps | Exhausted
"""How a run ends."""


@dataclass(frozen=True, slots=True)
class Instance:
    """4.5.3, a module instance with its store: global values, memory 0, and each table's
    function indices, None for a null element. A run writes them in place."""

    module: Module
    globals: list[int]
    memory: bytearray
    tables: list[list[int | None]]


class _StopError(Exception):
    """The run ends in `outcome`."""

    def __init__(self, outcome: Trap | OutOfSteps | Exhausted) -> None:
        super().__init__(outcome)
        self.outcome = outcome


class _BranchError(Exception):
    """`br depth`, on its way out to the label it targets."""

    def __init__(self, depth: int) -> None:
        super().__init__(depth)
        self.depth = depth


class _ReturnError(Exception):
    """`return`, on its way out to its function's call."""


class _TailCallError(Exception):
    """A tail call of `func` on `args`, on its way out to the caller's call driver."""

    def __init__(self, func: int, args: list[int]) -> None:
        super().__init__(func)
        self.func = func
        self.operands = args


@dataclass(slots=True)
class _Machine:
    """A run: its instance, the steps left, the calls active."""

    instance: Instance
    steps: int
    depth: int = 0


@dataclass(slots=True)
class _Frame:
    """4.2.13, a function's activation: its locals and its operand stack."""

    locals: list[int]
    stack: list[int]


def _trap_if(bad: bool, kind: TrapKind) -> None:
    """Trap with `kind` when `bad`."""
    if bad:
        raise _StopError(Trap(kind))


def _checked(result: int | Trap) -> int:
    """An operator's result, or its trap raised."""
    if isinstance(result, Trap):
        raise _StopError(result)
    return result


def _pop(frame: _Frame, count: int) -> list[int]:
    """The top `count` operands, removed, the deepest first."""
    cut = len(frame.stack) - count
    taken = frame.stack[cut:]
    del frame.stack[cut:]
    return taken


def _label(m: _Machine, frame: _Frame, body: Expr, height: int, arity: int) -> bool:
    """Runs `body` under a label (4.4.8) whose stack starts at `height` and whose branches carry
    `arity` values; True when a branch to this label ended it."""
    try:
        for instr in body:
            if m.steps == 0:
                raise _StopError(OutOfSteps())
            m.steps -= 1
            _EXECUTE[type(instr)](m, frame, instr)
    except _BranchError as branch:
        if branch.depth:
            raise _BranchError(branch.depth - 1) from None
        frame.stack[height:] = frame.stack[len(frame.stack) - arity :]
        return True
    return False


def _func_type(m: _Machine, func: int) -> FuncType:
    """The type of function `func`."""
    module = m.instance.module
    return module.types[module.funcs[func].type]


def _call(m: _Machine, func: int, args: list[int]) -> list[int]:
    """4.4.10, invokes `func` on `args` and gives its results; a tail call loops here."""
    _stop_if_exhausted(m)
    m.depth += 1
    try:
        while True:
            code = m.instance.module.funcs[func]
            frame = _Frame([*args, *[0] * len(code.locals)], [])
            arity = len(_func_type(m, func).results)
            try:
                _label(m, frame, code.body, 0, arity)
            except _TailCallError as tail:
                func, args = tail.func, tail.operands
                continue
            except _ReturnError:
                pass
            return frame.stack[len(frame.stack) - arity :]
    finally:
        m.depth -= 1


def _stop_if_exhausted(m: _Machine) -> None:
    """Ends the run when `DEPTH` calls are active already."""
    if m.depth == DEPTH:
        raise _StopError(Exhausted())


def _exec_const(_m: _Machine, frame: _Frame, instr: Const) -> None:
    """4.6.10, t.const c."""
    frame.stack.append(instr.value)


def _exec_unop(_m: _Machine, frame: _Frame, instr: Unop) -> None:
    """4.6.10, t.unop."""
    frame.stack.append(UNOPS[instr.op](WIDTH[instr.type], frame.stack.pop()))


def _exec_binop(_m: _Machine, frame: _Frame, instr: Binop) -> None:
    """4.6.10, t.binop: traps where the operator does."""
    i, j = _pop(frame, 2)
    frame.stack.append(_checked(BINOPS[instr.op](WIDTH[instr.type], i, j)))


def _exec_testop(_m: _Machine, frame: _Frame, instr: Testop) -> None:
    """4.6.10, t.testop."""
    frame.stack.append(TESTOPS[instr.op](WIDTH[instr.type], frame.stack.pop()))


def _exec_relop(_m: _Machine, frame: _Frame, instr: Relop) -> None:
    """4.6.10, t.relop."""
    i, j = _pop(frame, 2)
    frame.stack.append(RELOPS[instr.op](WIDTH[instr.type], i, j))


def _exec_cvtop(_m: _Machine, frame: _Frame, instr: Cvtop) -> None:
    """4.6.10, t2.cvtop_t1."""
    frame.stack.append(CVTOPS[instr.op](frame.stack.pop()))


def _exec_nop(_m: _Machine, _frame: _Frame, _instr: Nop) -> None:
    """4.6.1, nop."""


def _exec_unreachable(_m: _Machine, _frame: _Frame, _instr: Unreachable) -> None:
    """4.6.1, unreachable: traps."""
    raise _StopError(Trap("unreachable"))


def _exec_drop(_m: _Machine, frame: _Frame, _instr: Drop) -> None:
    """4.6.1, drop."""
    frame.stack.pop()


def _exec_select(_m: _Machine, frame: _Frame, _instr: Select) -> None:
    """4.6.1, select: the first operand unless the condition is 0."""
    first, second, condition = _pop(frame, 3)
    frame.stack.append(first if condition else second)


def _exec_local_get(_m: _Machine, frame: _Frame, instr: LocalGet) -> None:
    """4.6.6, local.get x."""
    frame.stack.append(frame.locals[instr.index])


def _exec_local_set(_m: _Machine, frame: _Frame, instr: LocalSet) -> None:
    """4.6.6, local.set x."""
    frame.locals[instr.index] = frame.stack.pop()


def _exec_local_tee(_m: _Machine, frame: _Frame, instr: LocalTee) -> None:
    """4.6.6, local.tee x."""
    frame.locals[instr.index] = frame.stack[-1]


def _exec_global_get(m: _Machine, frame: _Frame, instr: GlobalGet) -> None:
    """4.6.6, global.get x."""
    frame.stack.append(m.instance.globals[instr.index])


def _exec_global_set(m: _Machine, frame: _Frame, instr: GlobalSet) -> None:
    """4.6.6, global.set x: kept whatever follows, a trap included."""
    m.instance.globals[instr.index] = frame.stack.pop()


def _arity(m: _Machine, bt: BlockType) -> tuple[int, int]:
    """4.6.3, a block type's parameter and result counts."""
    match bt:
        case None:
            return 0, 0
        case TypeUse(index=k):
            t = m.instance.module.types[k]
            return len(t.params), len(t.results)
        case "i32" | "i64":
            return 0, 1
        case _:
            assert_never(bt)


def _exec_block(m: _Machine, frame: _Frame, instr: Block) -> None:
    """4.6.3, block: a branch to it continues after it with the block's results."""
    params, results = _arity(m, instr.type)
    _label(m, frame, instr.body, len(frame.stack) - params, results)


def _exec_loop(m: _Machine, frame: _Frame, instr: Loop) -> None:
    """4.6.3, loop: a branch to it starts it again with the loop's parameters."""
    params, _ = _arity(m, instr.type)
    while _label(m, frame, instr.body, len(frame.stack) - params, params):
        pass


def _exec_if(m: _Machine, frame: _Frame, instr: If) -> None:
    """4.6.3, if: the `then` arm unless the condition is 0, as a block."""
    condition = frame.stack.pop()
    params, results = _arity(m, instr.type)
    arm = instr.then if condition else instr.else_
    _label(m, frame, arm, len(frame.stack) - params, results)


def _exec_br(_m: _Machine, _frame: _Frame, instr: Br) -> None:
    """4.6.3, br l."""
    raise _BranchError(instr.label)


def _exec_br_if(_m: _Machine, frame: _Frame, instr: BrIf) -> None:
    """4.6.3, br_if l: branches unless the condition is 0."""
    if frame.stack.pop():
        raise _BranchError(instr.label)


def _exec_br_table(_m: _Machine, frame: _Frame, instr: BrTable) -> None:
    """4.6.3, br_table l* l_N: the i-th label, or the default past them."""
    i = frame.stack.pop()
    raise _BranchError(instr.labels[i] if i < len(instr.labels) else instr.default)


def _exec_return(_m: _Machine, _frame: _Frame, _instr: Return) -> None:
    """4.6.3, return."""
    raise _ReturnError


def _exec_call(m: _Machine, frame: _Frame, instr: Call) -> None:
    """4.6.3, call x."""
    args = _pop(frame, len(_func_type(m, instr.func).params))
    frame.stack.extend(_call(m, instr.func, args))


def _exec_return_call(m: _Machine, frame: _Frame, instr: ReturnCall) -> None:
    """4.6.3, return_call x: the caller's frame is gone before the call."""
    args = _pop(frame, len(_func_type(m, instr.func).params))
    raise _TailCallError(instr.func, args)


def _callee(m: _Machine, frame: _Frame, table: int, use: TypeUse) -> int:
    """4.6.3, the function `call_indirect` reaches through `table`, its type compared with
    `use`'s structurally: two type indices declaring the same FuncType match."""
    i = frame.stack.pop()
    elems = m.instance.tables[table]
    _trap_if(i >= len(elems), "undefined element")
    func = elems[i]
    if func is None:
        raise _StopError(Trap("uninitialized element"))
    wanted = m.instance.module.types[use.index]
    _trap_if(_func_type(m, func) != wanted, "indirect call type mismatch")
    return func


def _exec_call_indirect(m: _Machine, frame: _Frame, instr: CallIndirect) -> None:
    """4.6.3, call_indirect x y."""
    func = _callee(m, frame, instr.table, instr.type)
    args = _pop(frame, len(_func_type(m, func).params))
    frame.stack.extend(_call(m, func, args))


def _exec_return_call_indirect(m: _Machine, frame: _Frame, instr: ReturnCallIndirect) -> None:
    """4.6.3, return_call_indirect x y."""
    func = _callee(m, frame, instr.table, instr.type)
    raise _TailCallError(func, _pop(frame, len(_func_type(m, func).params)))


def _address(m: _Machine, frame: _Frame, arg: MemArg, size: int) -> int:
    """4.6.8, the effective address of an access of `size` bytes; traps past the memory."""
    at = frame.stack.pop() + arg.offset
    _trap_if(at + size > len(m.instance.memory), "out of bounds memory access")
    return at


def _exec_load(m: _Machine, frame: _Frame, instr: Load) -> None:
    """4.6.8, t.load and t.loadN_sx: little-endian, a narrow signed load sign-extended."""
    bits, sign = instr.pack or (WIDTH[instr.type], "u")
    at = _address(m, frame, instr.arg, bits // 8)
    raw = int.from_bytes(m.instance.memory[at : at + bits // 8], "little")
    frame.stack.append(signed(bits, raw) % (1 << WIDTH[instr.type]) if sign == "s" else raw)


def _exec_store(m: _Machine, frame: _Frame, instr: Store) -> None:
    """4.6.8, t.store and t.storeN: the value's low N bits, little-endian."""
    value = frame.stack.pop()
    size = (instr.size or WIDTH[instr.type]) // 8
    at = _address(m, frame, instr.arg, size)
    m.instance.memory[at : at + size] = (value % (1 << 8 * size)).to_bytes(size, "little")


def _exec_memory_size(m: _Machine, frame: _Frame, _instr: MemorySize) -> None:
    """4.6.8, memory.size: in pages."""
    frame.stack.append(len(m.instance.memory) // PAGE)


_EXECUTE: dict[type[Instr], Callable[[_Machine, _Frame, Any], None]] = {
    Const: _exec_const,
    Unop: _exec_unop,
    Binop: _exec_binop,
    Testop: _exec_testop,
    Relop: _exec_relop,
    Cvtop: _exec_cvtop,
    Nop: _exec_nop,
    Unreachable: _exec_unreachable,
    Drop: _exec_drop,
    Select: _exec_select,
    LocalGet: _exec_local_get,
    LocalSet: _exec_local_set,
    LocalTee: _exec_local_tee,
    GlobalGet: _exec_global_get,
    GlobalSet: _exec_global_set,
    Block: _exec_block,
    Loop: _exec_loop,
    If: _exec_if,
    Br: _exec_br,
    BrIf: _exec_br_if,
    BrTable: _exec_br_table,
    Return: _exec_return,
    Call: _exec_call,
    CallIndirect: _exec_call_indirect,
    ReturnCall: _exec_return_call,
    ReturnCallIndirect: _exec_return_call_indirect,
    Load: _exec_load,
    Store: _exec_store,
    MemorySize: _exec_memory_size,
}
"""4.6, how each instruction class executes."""


def closed(module: Module) -> bool:
    """A module the evaluator runs: no imports and no start function."""
    return not module.imports and module.start is None


def _constant(instance: Instance, expr: Expr) -> int:
    """4.6.12, the value of a constant expression."""
    frame = _Frame([], [])
    _label(_Machine(instance, len(expr)), frame, expr, 0, 1)
    return frame.stack[-1]


def _placed[T](target: MutableSequence[T], at: int, items: Sequence[T]) -> bool:
    """`items` copied into `target` from `at`, unless they reach past its end."""
    if at + len(items) > len(target):
        return False
    target[at : at + len(items)] = items
    return True


def instantiate(module: Module) -> Instance | Trap:
    """4.7.2, the instance of a closed module: globals from their constant expressions, then the
    active element and data segments in order; a segment past its table or memory traps.

    Refuses, with ValueError, a module that is not `closed`.
    """
    if not closed(module):
        msg = "the evaluator runs closed modules only: no imports, no start function"
        raise ValueError(msg)
    memory = bytearray(PAGE * sum(mem.type.limits.min for mem in module.mems))
    tables: list[list[int | None]] = [[None] * t.type.limits.min for t in module.tables]
    instance = Instance(module, [], memory, tables)
    for g in module.globals:
        instance.globals.append(_constant(instance, g.init))
    return _segmented(instance)


def _segmented(instance: Instance) -> Instance | Trap:
    """4.7.2, `instance` with its active element, then data, segments in place, in order."""
    for e in instance.module.elems:
        if not _placed(instance.tables[e.table], _constant(instance, e.offset), e.funcs):
            return Trap("out of bounds table access")
    for d in instance.module.datas:
        if not _placed(instance.memory, _constant(instance, d.offset), d.init):
            return Trap("out of bounds memory access")
    return instance


def invoke(instance: Instance, func: int, args: tuple[int, ...], steps: int) -> Outcome:
    """4.7.3, calls function `func` of `instance` on `args` with a budget of `steps`
    instructions; the run's writes to the instance stay, whatever the outcome."""
    machine = _Machine(instance, steps)
    try:
        return Values(tuple(_call(machine, func, list(args))))
    except _StopError as stop:
        return stop.outcome
