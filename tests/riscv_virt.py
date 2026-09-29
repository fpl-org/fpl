"""Not a test: the QEMU virt frame, the text a printed program runs inside.

The frame is Zicsr and privileged text outside the IR, so it lives here as text, not in
`fpl.asm.riscv` (hole `virt-frame-home`). This is the minimal frame: it supplies `_start`
before the program and the spin after it. The program itself reports: bytes stored to the
UART's transmit register, and a word stored to the test device, whose low half 0x3333 asks
QEMU to exit with the high half as its status (0x5555 exits 0).
"""

UART = 0x1000_0000  # the 16550 on virt: a byte stored here is a byte on -serial stdio
TEST_DEVICE = 0x10_0000  # sifive_test on virt
HEAD = "\t.text\n\t.globl\t_start\n_start:\n"
# QEMU finishes asynchronously after the test-device store: without the spin the hart runs on
# into whatever follows, traps, and a second report may win (probe log 5).
SPIN = "\tjal\tx0, .\n"


def framed(program_text: str) -> str:
    """`program_text` between `_start` and the spin: a whole source for `assemble`."""
    return HEAD + program_text + SPIN
