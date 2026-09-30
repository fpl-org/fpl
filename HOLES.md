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
- Default in force: no per-test settings; oracle tests run at the harness profile's example counts (quick 100), because the house rule forbids max_examples or a per-test @settings count in a test; measured at quick with pytest --durations on fc3b95e, warm: checked-programs-halt 11.4 s and evaluator-agrees-with-qemu 11.1 s (100 batches of up to 20 blocks of up to 20 instructions each), print-is-disassembly 4.8 s, control-targets-agree 5.1 s, checker-agrees-per-program 4.8 s, no-silent-relaxation 5.3 s, checker-agrees-per-line 2.0 s, virt-smoke 1.0 s: 45.8 s for the two oracle files, against the 6 s oracle-budget; make check took 67 s wall on the tree of fc3b95e; on 0c6d28c, with window-agrees and traps-agree, pytest --durations (warm, serial): checked-programs-halt 12.8 s, window-agrees 12.7 s, evaluator-agrees-with-qemu 12.2 s, traps-agree 11.1 s, virt-smoke 5.6 s (the first call, toolchain resolution included), the llvm file 23.6 s: 78.0 s for the two oracle files; make check's pytest step took 83.1 s
- Closes by: PSJ, sanctioning the design's ORACLE override (backend="hypothesis", max_examples 10/50/10), or adding a harness-level oracle profile in quality/noslop_pytest.py; at 10 examples the two QEMU laws would cost about 1.1 s each
- Evidence: design section 7 "Budgets" (ORACLE settings, "PSJ's to veto (question 1)") and section 8 oracle-settings; implementer rule "Never put max_examples or a per-test @settings count in a test"; pytest --durations on b62fb41 and fc3b95e

## harness-registers
- Depends on it: tests/riscv_strategies.py (FRAME_FORMS, forms), tests/riscv_virt.py (batch), tests/test_riscv_via_qemu.py
- Default in force: blocks run in the QEMU virt frame neither read nor write x3 (the window, unit 6) or x4 (the frame's record): FRAME_FORMS draws every register operand from the other 30, while FORMS, for the llvm oracles, draws all 32; the checker does not know this; the reports compare x1..x31 but x4, and x3 is loaded and saved like any other register until unit 6 points it at the window
- Closes by: M's register roles and H0's calling convention (C3a), which name reserved registers; the design, confirming that reads are excluded too (it says "excluding x3 and x4 when writable": QEMU's x4 is the record's address, so a block reading it would diverge from the evaluator's)
- Evidence: design section 6 regs(writable=True) and section 8 harness-registers; prompt "registers the frame reserves (x3, x4)"; tests/riscv_virt.py batch

## traps-are-root-panics
- Depends on it: fpl/asm/riscv/eval.py (Trapped), tests/test_riscv_eval.py; later tests/riscv_virt.py (trap handler) and tests/test_riscv_via_qemu.py (traps-agree)
- Default in force: a trap is observed, not handled: ecall ends the run as Trapped(11, index, machine) and ebreak as Trapped(3, ...), the M-mode causes on QEMU virt; the frame is to report (mcause, mepc) and resume at the next block; no IR construct handles a trap; FPL's Fail never lowers to a trap; RV64IM has no GC types or exceptions, so the GC-and-exceptions hole of track B has no instruction to exclude here
- Closes by: PSJ confirming row 81 (3) and row 43 for RISC-V; H2's handler set replaces the frame's handler
- Evidence: design section 5 (System) and section 8; row 81 (3) "Wasm traps ... correspond to a root panic (row 43)"; probe: ecall exit 11, ebreak 3, illegal 2, load from 0x4 exit 5

## jalr-misaligned-target
- Depends on it: fpl/asm/riscv/eval.py (indirect), tests/test_riscv_eval.py (jalr to BASE + 2)
- Default in force: a jalr target inside the program but not 4-aligned ends the run as Unmodelled, the mechanism the design gives a target outside [base, base + 4n); without C, hardware raises instruction-address-misaligned (cause 0) instead
- Closes by: the design, choosing Trapped(0, index) with a QEMU probe in traps-agree, or keeping Unmodelled
- Evidence: design section 5 names only targets outside [base, base + 4n); spec 20250508 2.5.1 (jalr), fpl/asm/riscv/eval.py indirect()

## misaligned-access
- Depends on it: fpl/asm/riscv/eval.py (access), tests/test_riscv_eval.py (stores and loads at any offset), tests/riscv_strategies.py (in_window, memory_code), tests/test_riscv_via_qemu.py (window-agrees)
- Default in force: a misaligned load or store inside the window completes, little-endian, like an aligned one, as QEMU 10.2.4 virt does; memory_code draws misaligned offsets on purpose and window-agrees compares them with QEMU
- Closes by: H2 or E, when the bare-metal EEI is written down
- Evidence: spec 20250508 section 2.6 (misaligned accesses are the execution environment's choice); design section 5 (Memory) and section 8; design section 11 probe log 5: ld 1(x5), sd 2(x5) at 0x80001001/2 exit 0; fpl/asm/riscv/eval.py:324

## window-base
- Depends on it: fpl/asm/riscv/eval.py (run, Code.window), tests/riscv_virt.py (framed_block: addi x3, x4, 496), tests/test_riscv_via_qemu.py (start)
- Default in force: the window's first byte is at the address x3 holds when `run` starts, read once; a block that wrote x3 would not move its window, and a later access through the new x3 would be measured from the old base; the frame never lets a block write x3 (hole harness-registers), and the oracle test reads the window's address from x3's slot of QEMU's report, since the records are .L labels in .data that llvm-objdump -d does not list
- Closes by: the design, choosing x3 at entry, x3 at each access, or a window address carried in Machine apart from the registers; or M's register roles, when they name x3
- Evidence: design section 5 "256 bytes at the address in x3" (it does not say when x3 is read); fpl/asm/riscv/eval.py:402; tests/test_riscv_via_qemu.py:122
