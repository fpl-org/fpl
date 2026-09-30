"""The checker against the ranges llvm-mc 21.1.8 enforces, in process: each boundary, both sides."""

from collections.abc import Callable

import pytest
from hypothesis import given
from hypothesis import strategies as st
from riscv_strategies import Invalid, forward_branching, invalid_programs, padded

from fpl.asm.riscv.check import Kind, Problem, check
from fpl.asm.riscv.model import (
    Branch,
    I,
    Instr,
    Jal,
    Jalr,
    Label,
    Load,
    OpBranch,
    OpI,
    OpLoad,
    OpShift,
    OpStore,
    OpUpper,
    Program,
    Reg,
    Shift,
    Store,
    Upper,
)

# One builder per ranged operand, taking the operand's value, with its kind and inclusive range.
RANGED: tuple[tuple[Callable[[int], Instr], Kind, int, int], ...] = (
    (lambda v: I(OpI.ADDI, Reg.X1, Reg.X2, v), Kind.IMM12, -2048, 2047),
    (lambda v: I(OpI.ADDIW, Reg.X1, Reg.X2, v), Kind.IMM12, -2048, 2047),
    (lambda v: Load(OpLoad.LD, Reg.X1, Reg.X2, v), Kind.IMM12, -2048, 2047),
    (lambda v: Store(OpStore.SB, Reg.X1, Reg.X2, v), Kind.IMM12, -2048, 2047),
    (lambda v: Jalr(Reg.X1, Reg.X2, v), Kind.IMM12, -2048, 2047),
    (lambda v: Shift(OpShift.SRAI, Reg.X1, Reg.X2, v), Kind.SHAMT6, 0, 63),
    (lambda v: Shift(OpShift.SLLIW, Reg.X1, Reg.X2, v), Kind.SHAMT5, 0, 31),
    (lambda v: Upper(OpUpper.AUIPC, Reg.X1, v), Kind.IMM20, 0, 1048575),
)


def kinds(program: Program) -> list[tuple[int | None, Kind]]:
    """Where and what the checker objects to, its details left out."""
    return [(problem.index, problem.kind) for problem in check(program)]


@given(st.sampled_from(RANGED), st.data())
def test_a_ranged_operand_is_a_problem_exactly_outside_its_range(
    ranged: tuple[Callable[[int], Instr], Kind, int, int], data: st.DataObject
) -> None:
    """An immediate, offset or shift amount is one problem of its kind iff it leaves its range.

    The detail names the value and the range.
    """
    build, kind, low, high = ranged
    edge = st.sampled_from((low - 1, low, high, high + 1))
    value = data.draw(st.one_of(edge, st.integers(low - 4096, high + 4096), st.integers()))
    expected = [] if low <= value <= high else [(0, kind)]
    assert kinds((build(value),)) == expected
    assert all(f"{value} is outside [{low}, {high}]" in p.detail for p in check((build(value),)))


@given(forward_branching(20))
def test_a_valid_program_has_no_problems(program: Program) -> None:
    assert check(program) == ()


BEQ = Branch(OpBranch.BEQ, Reg.X1, Reg.X2, Label(".Lt"))
JAL = Jal(Reg.X0, Label(".Lt"))


@pytest.mark.parametrize(
    ("jump", "offset", "problem"),
    [
        (BEQ, 4092, None),
        (BEQ, 4096, Kind.BRANCH_RANGE),
        (BEQ, -4096, None),
        (BEQ, -4100, Kind.BRANCH_RANGE),
        (BEQ, 0, None),
        (JAL, 1048572, None),
        (JAL, 1048576, Kind.JAL_RANGE),
        (JAL, -1048576, None),
        (JAL, -1048580, Kind.JAL_RANGE),
    ],
)
def test_a_jump_is_a_problem_exactly_past_its_reach(
    jump: Branch | Jal, offset: int, problem: Kind | None
) -> None:
    """Offsets are 4 x (label's instruction index - jump's): the realizable edges are 4092, 4096."""
    program = padded(jump, offset)
    at = next(i for i, item in enumerate(program) if isinstance(item, Branch | Jal))
    assert kinds(program) == ([] if problem is None else [(at, problem)])


def test_a_second_definition_is_a_duplicate_and_the_first_is_the_target() -> None:
    program = (Label(".La"), JAL, Label(".La"), Label(".Lt"), Label(".La"))
    assert kinds(program) == [(2, Kind.DUPLICATE_LABEL), (4, Kind.DUPLICATE_LABEL)]


def test_an_undefined_label_is_one_whole_program_problem_per_name() -> None:
    program = (JAL, BEQ, Jal(Reg.X1, Label(".Lb")))
    assert check(program) == (
        Problem(None, Kind.UNDEFINED_LABEL, ".Lt is referenced but never defined"),
        Problem(None, Kind.UNDEFINED_LABEL, ".Lb is referenced but never defined"),
    )


@pytest.mark.parametrize("name", ["", ".L", "L1", ".l1", ".L-1", ".L1 ", "_start", ".L1\n"])
def test_a_label_outside_the_dot_l_form_is_a_problem_where_defined_and_where_used(
    name: str,
) -> None:
    program = (Label(name), Jal(Reg.X0, Label(name)))
    assert kinds(program) == [(0, Kind.LABEL_NAME), (1, Kind.LABEL_NAME)]


@given(invalid_programs())
def test_the_checker_names_exactly_the_violations_put_into_a_valid_program(case: Invalid) -> None:
    """Each operand out of range, second definition and undefined target, and nothing else."""
    assert set(kinds(case.program)) == case.problems


def test_each_problem_says_what_it_refuses() -> None:
    nops = [I(OpI.ADDI, Reg.X0, Reg.X0, 0)] * 1024
    program: Program = (
        BEQ,
        *nops,
        Label(".Lt"),
        Label(".Lt"),
        Label("Lx"),
        I(OpI.ADDI, Reg.X1, Reg.X0, 2048),
    )
    assert set(check(program)) == {
        Problem(0, Kind.BRANCH_RANGE, "beq to .Lt: 4100 is outside [-4096, 4094]"),
        Problem(1026, Kind.DUPLICATE_LABEL, ".Lt is already defined"),
        Problem(1027, Kind.LABEL_NAME, "label 'Lx' is not .L[A-Za-z0-9_]+"),
        Problem(1028, Kind.IMM12, "addi 2048 is outside [-2048, 2047]"),
    }
