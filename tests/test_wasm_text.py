"""The printer of fpl.asm.wasm writes WAT that wabt assembles, and names that survive it."""

import re

from hypothesis import given
from wasm_oracle import Tools, wat2wasm
from wasm_strategies import BinopMain, binop_mains

from fpl.asm.wasm.module import Module
from fpl.asm.wasm.text import print_module


def unescape(literal: str) -> bytes:
    """The bytes a WAT string literal's body stands for (6.3.3), for `\\hh` escapes only."""
    return re.sub(rb"\\([0-9a-f]{2})", lambda m: bytes([int(m[1], 16)]), literal.encode())


@given(binop_mains(unused=True))
def test_a_printed_module_assembles_and_keeps_its_export_name(
    wasm_tools: Tools, case: BinopMain
) -> None:
    module: Module = case.module()
    text = print_module(module)
    done = wat2wasm(wasm_tools, text)
    assert done.returncode == 0, f"{text}\n{done.stderr}"
    literal = re.search(r'\(export "([^"]*)" \(func 0\)\)', text)
    assert literal is not None, text
    assert unescape(literal[1]) == case.name.encode()
