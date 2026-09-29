"""The model is the chapter 35 listing of RV64IM, one to one (spec 20250508)."""

import inspect

from hypothesis import given
from riscv_strategies import instructions

from fpl.asm.riscv import model
from fpl.asm.riscv.model import (
    CLASSES,
    Bare,
    Branch,
    Fence,
    I,
    Instr,
    Jal,
    Jalr,
    Load,
    R,
    Shift,
    Store,
    Upper,
    mnemonics,
)

# Chapter 35, "RV32/64G Instruction Set Listings", in its order: RV32I without PAUSE (41 rows),
# the RV64I rows that are new (12; its SLLI, SRLI and SRAI redefine the RV32I rows with a 6-bit
# shamt, so those rows carry 4.2.1), RV32M (8), RV64M (5). Each row: mnemonic, the section of
# the 20250508 release that defines it, the class that holds it.
LISTING: tuple[tuple[str, str, type[Instr]], ...] = (
    ("lui", "2.4.1", Upper),
    ("auipc", "2.4.1", Upper),
    ("jal", "2.5.1", Jal),
    ("jalr", "2.5.1", Jalr),
    ("beq", "2.5.2", Branch),
    ("bne", "2.5.2", Branch),
    ("blt", "2.5.2", Branch),
    ("bge", "2.5.2", Branch),
    ("bltu", "2.5.2", Branch),
    ("bgeu", "2.5.2", Branch),
    ("lb", "2.6", Load),
    ("lh", "2.6", Load),
    ("lw", "2.6", Load),
    ("lbu", "2.6", Load),
    ("lhu", "2.6", Load),
    ("sb", "2.6", Store),
    ("sh", "2.6", Store),
    ("sw", "2.6", Store),
    ("addi", "2.4.1", I),
    ("slti", "2.4.1", I),
    ("sltiu", "2.4.1", I),
    ("xori", "2.4.1", I),
    ("ori", "2.4.1", I),
    ("andi", "2.4.1", I),
    ("slli", "4.2.1", Shift),
    ("srli", "4.2.1", Shift),
    ("srai", "4.2.1", Shift),
    ("add", "2.4.2", R),
    ("sub", "2.4.2", R),
    ("sll", "2.4.2", R),
    ("slt", "2.4.2", R),
    ("sltu", "2.4.2", R),
    ("xor", "2.4.2", R),
    ("srl", "2.4.2", R),
    ("sra", "2.4.2", R),
    ("or", "2.4.2", R),
    ("and", "2.4.2", R),
    ("fence", "2.7", Fence),
    ("fence.tso", "2.7", Bare),
    ("ecall", "2.8", Bare),
    ("ebreak", "2.8", Bare),
    ("lwu", "4.3", Load),
    ("ld", "4.3", Load),
    ("sd", "4.3", Store),
    ("addiw", "4.2.1", I),
    ("slliw", "4.2.1", Shift),
    ("srliw", "4.2.1", Shift),
    ("sraiw", "4.2.1", Shift),
    ("addw", "4.2.2", R),
    ("subw", "4.2.2", R),
    ("sllw", "4.2.2", R),
    ("srlw", "4.2.2", R),
    ("sraw", "4.2.2", R),
    ("mul", "12.1", R),
    ("mulh", "12.1", R),
    ("mulhsu", "12.1", R),
    ("mulhu", "12.1", R),
    ("div", "12.2", R),
    ("divu", "12.2", R),
    ("rem", "12.2", R),
    ("remu", "12.2", R),
    ("mulw", "12.1", R),
    ("divw", "12.2", R),
    ("divuw", "12.2", R),
    ("remw", "12.2", R),
    ("remuw", "12.2", R),
)


@given(instructions())
def test_the_model_is_the_listing_one_to_one(instr: Instr) -> None:
    """[law: listing-one-to-one] The op enums and the fixed ops are exactly the 66 rows.

    No mnemonic twice, none missing, none extra, each under the class the listing names, PAUSE
    absent; and every instruction the strategies draw is one of those rows.
    """
    held = [(mnemonic, form) for form in CLASSES for mnemonic in mnemonics(form)]
    listed = {mnemonic: form for mnemonic, _, form in LISTING}
    assert len(held) == len(dict(held)) == len(LISTING) == 66
    assert dict(held) == listed
    assert "pause" not in listed
    assert listed[instr.op] is type(instr)


def test_each_mnemonic_is_doc_commented_with_its_section() -> None:
    source = inspect.getsource(model)
    for mnemonic, section, _ in LISTING:
        assert source.count(f'= "{mnemonic}"  # {section}\n') == 1, mnemonic
