"""The assembly layer: machine code as frozen values, free of FPL.

Nothing under `fpl.asm` imports anything from `fpl` outside `fpl.asm` (the import-linter
contract `asm-stands-alone`, and the law `fpl-free` in tests/test_riscv_free.py).
"""
