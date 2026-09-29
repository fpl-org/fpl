"""The oracles of fpl.asm.wasm: pinned, resolved once, and able to fail."""

from collections.abc import Callable
from typing import Literal, get_args

import pytest
from hypothesis import given
from hypothesis import strategies as st
from wasm_oracle import (
    RESOLVE,
    STORE,
    VERSIONS,
    Item,
    OracleError,
    Run,
    Tools,
    Verdict,
    resolve,
    run_wabt,
    run_wasmtime,
    store_paths,
    versions,
)
from wasm_strategies import BinopMain, binop_mains

from fpl.asm.wasm.instr import IBinop
from fpl.asm.wasm.text import print_module
from fpl.asm.wasm.types import WIDTH, NumType

store_lines = st.text(alphabet="abc0123456789-./", min_size=1).map(lambda rest: STORE + rest)
other_lines = st.sampled_from(["", "==> wiring the git hooks", "wat2wasm", " /nix/store/x"])


@given(st.lists(store_lines | other_lines, max_size=4))
def test_the_oracles_are_the_pinned_store_paths(wasm_tools: Tools, lines: list[str]) -> None:
    """[law: oracle-pinned] Resolution takes exactly one /nix/store/ line per tool, no more.

    The fixture resolved wabt 1.0.41 and wasmtime 45.0.2 from the worktree's own wasm layer;
    every binary it hands out is an absolute path into the store; and of any stdout the resolving
    command could print, only exactly two /nix/store/ lines are accepted.
    """
    exact = len(lines) == 2 and all(line.startswith(STORE) for line in lines)
    assert (store_paths("".join(line + "\n" for line in lines)) is not None) == exact
    every = (
        wasm_tools.wat2wasm,
        wasm_tools.wast2json,
        wasm_tools.spectest_interp,
        wasm_tools.wasm_validate,
        wasm_tools.wasmtime,
    )
    assert all(path.is_absolute() and str(path).startswith(STORE) for path in every)
    assert versions(wasm_tools) == VERSIONS


def test_without_nix_resolving_is_an_error() -> None:
    with pytest.raises(OracleError, match="/nonexistent/nix develop"):
        resolve(RESOLVE.replace("nix develop", "/nonexistent/nix develop", 1))


def binops(n: int) -> dict[IBinop, Callable[[int, int], int]]:
    """The integer binary operators of width n on unsigned operands, before wrapping (4.3.2)."""

    def signed(v: int) -> int:
        return v - (1 << n) if v >> (n - 1) else v

    def quotient(a: int, b: int) -> int:
        q = abs(signed(a)) // abs(signed(b))
        return q if (signed(a) < 0) == (signed(b) < 0) else -q

    return {
        "add": lambda a, b: a + b,
        "sub": lambda a, b: a - b,
        "mul": lambda a, b: a * b,
        "div_u": lambda a, b: a // b,
        "rem_u": lambda a, b: a % b,
        "div_s": quotient,
        "rem_s": lambda a, b: signed(a) - signed(b) * quotient(a, b),
        "and": lambda a, b: a & b,
        "or": lambda a, b: a | b,
        "xor": lambda a, b: a ^ b,
        "shl": lambda a, b: a << b % n,
        "shr_u": lambda a, b: a >> b % n,
        "shr_s": lambda a, b: signed(a) >> b % n,
        "rotl": lambda a, b: a << b % n | a >> (n - b % n),
        "rotr": lambda a, b: a >> b % n | a << (n - b % n),
    }


def expected(case: BinopMain) -> tuple[tuple[NumType, int], ...] | str:
    """What main returns, computed from Python ints, or the message of its trap."""
    n = WIDTH[case.type]
    if case.op in ("div_s", "div_u", "rem_s", "rem_u") and case.b == 0:
        return "integer divide by zero"
    if case.op == "div_s" and (case.a, case.b) == (1 << (n - 1), (1 << n) - 1):
        return "integer overflow"
    return ((case.type, binops(n)[case.op](case.a, case.b) % (1 << n)),)


def run(case: BinopMain) -> Run:
    return Run(print_module(case.module()), expected(case))


batches = st.lists(binop_mains(), min_size=1, max_size=8)


@given(batches)
def test_a_batch_of_binops_returns_what_python_computes(
    wasm_tools: Tools, cases: list[BinopMain]
) -> None:
    items: list[Item] = [run(case) for case in cases]
    for report in (run_wabt(wasm_tools, items), run_wasmtime(wasm_tools, items)):
        assert report.wrong == (), report.output


Corruption = Literal["value", "wrapped", "token"]


def corrupt(item: Run, how: Corruption) -> Item:
    """The item made wrong: a wrong result, a valid module claimed invalid, a malformed token."""
    match how:
        case "wrapped":
            return Verdict(item.module, valid=False)
        case "token":
            return Run("(module\n  bogus" + item.module.removeprefix("(module"), item.expect)
        case "value":
            if isinstance(item.expect, str):
                return Run(item.module, (("i32", 0),))
            ((t, value),) = item.expect
            return Run(item.module, ((t, (value + 1) % (1 << WIDTH[t])),))


@given(batches, st.data())
def test_a_corrupted_item_fails_each_engine_by_its_index(
    wasm_tools: Tools, cases: list[BinopMain], data: st.DataObject
) -> None:
    """[law: oracle-bites] One corrupted item in a batch fails each engine, named by its index.

    The rest of the batch is sound, runs and valid modules mixed; the corruption is a wrong
    assert_return value, a valid module wrapped as invalid, or a malformed token that makes
    wast2json reject the whole script at batch.wast:L:C.
    """
    items: list[Item] = [
        Verdict(run(case).module, valid=True) if data.draw(st.booleans()) else run(case)
        for case in cases
    ]
    k = data.draw(st.integers(min_value=0, max_value=len(items) - 1))
    items[k] = corrupt(run(cases[k]), data.draw(st.sampled_from(get_args(Corruption))))
    for report in (run_wabt(wasm_tools, items), run_wasmtime(wasm_tools, items)):
        assert report.wrong == (k,), report.output
