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

## asm-syntax-authority
- Depends on it: fpl/asm/riscv/text.py, tests/test_riscv_text.py, tests/test_riscv_via_llvm.py
- Default in force: the printed form is what llvm-objdump 21.1.8 prints with -M no-aliases -M numeric --no-print-imm-hex, and it must assemble with llvm-mc 21.1.8
- Closes by: PSJ or palimpsest, adopting the RISC-V Assembly Programmer's Manual once it is ratified, or GNU as as a second oracle (hole gnu-as-unchecked)
- Evidence: github.com/riscv-non-isa/riscv-asm-manual release v0.0.1 (2025-02-05), a draft; design section 8
- Out-of-subset mnemonics are excluded by construction only: llvm-mc 21.1.8 accepts `fence.i` and `csrw` even under `-mattr=+m,-zicsr,-zifencei` (design section 11, probe log 7), so no oracle refuses a line outside RV64IM; the model has no constructor for one

## gnu-as-unchecked
- Depends on it: fpl/asm/riscv/text.py, prompt C "a printer in GNU assembler syntax"
- Default in force: only LLVM's integrated assembler checks the text; GNU as is not run
- Closes by: PSJ, adding pkgsCross.riscv64.buildPackages.binutils (cached for x86_64-linux, built from source on aarch64-darwin) as a second assembler oracle
- Evidence: map backend-bc §6.1 (riscv64 binutils 2.46 not cached on darwin); design section 8

## oracle-settings
- Depends on it: tests/test_riscv_via_llvm.py, tests/test_riscv_via_qemu.py, the law oracle-budget
- Default in force: no per-test settings; oracle tests run at the harness profile's example counts (quick 100), because the house rule forbids max_examples or a per-test @settings count in a test; measured at quick, print-is-disassembly takes 5.4 s and control-targets-agree 5.2 s, already past the 6 s oracle-budget for all oracle laws
- Closes by: PSJ, sanctioning the design's ORACLE override (backend="hypothesis", max_examples 10/50/10), or adding a harness-level oracle profile in quality/noslop_pytest.py
- Evidence: design section 7 "Budgets" (ORACLE settings, "PSJ's to veto (question 1)") and section 8 oracle-settings; implementer rule "Never put max_examples or a per-test @settings count in a test"; pytest --durations on b62fb41
