## virt-frame-home
- Depends on it: tests/riscv_virt.py, tests/test_riscv_via_qemu.py
- Default in force: the QEMU virt frame (today `_start` and the spin `jal x0, .`; later csrw mtvec, csrr mcause/mepc, mret, the UART and test-device addresses) is fixed text in tests/, outside the IR and outside coverage
- Closes by: E's author, promoting a runtime frame into fpl/asm/riscv when E runs lowered programs, or H2
- Evidence: prompt C "Not now: ... the privileged ISA (H2's)"; row 38 step 4 "hello over serial on QEMU virt"; design section 1 "Why the frame lives in tests/"

## spec-version
- Depends on it: fpl/asm/riscv/model.py (docstrings, section numbers), tests/test_riscv_text.py (GOLDEN), the chapter 35 listing table of the listing-one-to-one law
- Default in force: RISC-V Unprivileged ISA 20250508
- Closes by: PSJ, moving to a later named release; the listing test names every row that moved
- Evidence: gh api repos/riscv/riscv-isa-manual/releases: 20250508 is the newest release with a version name; design section 2
