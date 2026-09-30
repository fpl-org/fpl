# Holes

## frame-home
- Depends on it: tests/aarch64_frame.py
- Default in force: the frame (mrs/msr nzcv, libSystem calls, svc) is fixed text in tests/, outside the IR and outside coverage
- Closes by: E's author, promoting a runtime frame into fpl/asm/aarch64 when lowered programs run natively
- Evidence: prompt G "Not now: ... calls through the platform ABI"; design.md section 1, "Why the frame lives in tests/"

## spec-version
- Depends on it: fpl/asm/aarch64/model.py docstrings, fpl/asm/aarch64/alias.py, tests/test_aarch64_model.py (the 105-row table, when it lands)
- Default in force: DDI 0487 M.d (2026-09-29), PDF sha256 80d589a4645feba6bdb9d77edfaf04d4394d5d5444a4c41f97cf4fdd20eee3d5
- Closes by: PSJ, moving to a later release; the listing test names every page that moved
- Evidence: documentation-service.arm.com/documentation/ddi0487/versions lists md first; M.c's Part C headings are identical (design.md section 2)

## elf-route-unrun
- Depends on it: tests/aarch64_frame.py (Linux flavour), tests/aarch64_oracle.py (Linux route), tests/test_aarch64_via_run.py
- Default in force: the static ELF route (ld.lld -static -e _start, qemu-aarch64, svc #0) is written but has not been run; only the Darwin route ran (native-smoke green on this Mac)
- Closes by: the first CI run of the draft PR on ubuntu-latest, which runs every run law under qemu-aarch64
- Evidence: design.md section 8, probe 10: no Linux host, Docker daemon not running; qemu-user 10.2.4 cached for x86_64-linux

## first-exec-cost
- Depends on it: tests/test_aarch64_via_run.py (RUN settings)
- Default in force: every run batch is a freshly linked, ad-hoc signed Mach-O whose first execution costs 126-300 ms on macOS; run laws draw 4 examples at the quick profile, and checked-programs-run and evaluator-agrees-with-run share one batch per example
- Closes by: PSJ, either accepting the cost, or granting the terminal Developer Tools permission (a system security setting, his to change), or a persistent runner that maps code with MAP_JIT (not a linked executable, so it would change the oracle)
- Evidence: design.md section 7, probe: ten fresh links 126-300 ms, the same binary rerun 2 ms; at 0b8f17c under load average 31-34 the register run batch took 1.17 s and window-agrees 0.94 s at 4 examples

## alias-divergence
- Depends on it: fpl/asm/aarch64/alias.py (the rows with spec_differs: BITFIELD's bfi, LOGICAL_IMM's mov), tests/test_aarch64_via_llvm.py (test_every_alias_row_prints_as_llvm_objdump_prints_it)
- Default in force: where llvm-objdump's preferred disassembly differs from the C6.2 "Alias is preferred when" condition, the printer follows llvm-objdump; known: BFM with Rn = 11111 and imms < immr prints bfi, the spec prefers BFC (C6.2.37, C6.2.39); ORR (immediate) with Rn = 11111 prints mov exactly when no MOVZ or MOVN makes the value at the width (LLVM's isAnyMOVWMovAlias), where the spec's !MoveWidePreferred (C6.2.301, J1.2) also prefers mov for some values MOVN makes
- Closes by: PSJ or palimpsest, choosing the spec's text and a normalising oracle, or LLVM printing BFC by default
- Evidence: design.md section 8; probe: `bfm x1, xzr, #61, #2` disassembles as `bfi x1, xzr, #3, #3` on aarch64-linux-gnu and arm64-apple-macos14.0; `orr x0, xzr, #0xfffffffffffeffff` (N 1, immr 47, imms 62, so !MoveWidePreferred) disassembles as orr, `orr x0, xzr, #0xffff0000ffff0000` as mov

## asm-syntax-authority
- Depends on it: fpl/asm/aarch64/text.py, fpl/asm/aarch64/alias.py, tests/aarch64_oracle.py (disassemble), tests/test_aarch64_via_llvm.py
- Default in force: the printed form is llvm-objdump 21.1.8's default disassembly (aliases, --no-print-imm-hex) of -triple=aarch64-linux-gnu objects, and it must assemble with llvm-mc 21.1.8 to the same bytes
- Closes by: PSJ or palimpsest, adopting the Arm ARM's assembler syntax (C1.2) with GNU as as a second oracle
- Evidence: C1.4; design.md section 3; probe: 159 forms over all 105 pages, default text reassembled to identical bytes, -M no-aliases changed 8

## sp-unobserved
- Depends on it: fpl/asm/aarch64/eval.py (step), tests/test_aarch64_eval.py (test_unmodelled), tests/aarch64_strategies.py (straight_line, forward_branching never draw sp)
- Default in force: forms that read or write sp are checked by the text and checker laws only; the evaluator has no sp and returns Unmodelled for any instruction with sp in a register slot (found by check.slots), and no run observes sp
- Closes by: E or H0, when a frame gives blocks a stack of their own
- Evidence: design.md sections 5 and 8; fpl/asm/aarch64/eval.py:657; probe: the frame's sp is ASLR'd per run, and blocks must not move it (records are sp-relative)

## harness-registers
- Depends on it: tests/aarch64_strategies.py (GENERAL, regs, block, memory_code, memory_block), tests/aarch64_frame.py (OBSERVED, setup, based)
- Default in force: generated code never reads or writes x18, x29 or sp; memory blocks also keep x27 and x28 (the window's bases, which the frame sets) and one drawn index register, holding [0, 31] and used only as the register offset, out of every transfer slot (tests/aarch64_strategies.py, memory_code); the frame sets and stores only the other 29 registers, and a Block holds 0 for x18 and x29, which no block reads; the checker does not know this
- Closes by: M's register roles and H0's calling convention (C3a), which name reserved registers per target
- Evidence: design.md sections 6 and 8; Apple, "Writing ARM64 code for Apple platforms": "The platforms reserve register x18. Don't use this register." and "The frame pointer register (x29) must always address a valid frame record."

## oracle-settings
- Depends on it: tests/test_aarch64_via_run.py (RUN), tests/test_aarch64_via_llvm.py
- Default in force: the run laws use RUN = settings(backend="hypothesis", deadline=None, max_examples 4/20/4 for quick/harden/symbolic), and checked-programs-run and evaluator-agrees-with-run assert on one shared batch of one to eight blocks per example (blocks(k=8)); the llvm oracle tests carry backend="hypothesis" only and run at the profile's 100/2000/50, not the design's 10/50/10
- Closes by: PSJ, accepting, or asking for a harness-level oracle profile in quality/noslop_pytest.py
- Evidence: design.md section 7 (Budgets); measured on this Mac: the run law, quick 4 examples 1.2 s, harden 20 examples 20.2 s under load average 27; at 0b8f17c (ORACLE 10/50/10) full serial pytest 54.6 s, oracle calls 24.2 s of it (toolchain() 13.8 s, the rest 10.3 s), make check 109 s, load average 28-34 on 8 cores: over the 6 s budget, not idle

## misaligned-access
- Depends on it: fpl/asm/aarch64/eval.py (inside, transfer), tests/aarch64_strategies.py (memory_code), tests/test_aarch64_via_run.py (test_memory_blocks_leave_the_window_the_evaluator_leaves, test_memory_blocks_reach_misaligned_accesses)
- Default in force: a misaligned access inside the window completes, little-endian, as it does natively on Apple silicon at EL0; the evaluator checks only that every byte is inside the window, never the alignment
- Closes by: E or H0, when the target's memory model is written down
- Evidence: B2.8.2; design.md section 5 and probe 9 (stur/ldur at +1, stp/ldp at +3, ldrsh at +17 on the stack, exit 0); native: window-agrees green in make check at 265ad6d on this Mac, over memory_code blocks whose unscaled accesses sit at any byte offset and whose x27 writebacks move by single bytes (test_memory_blocks_reach_misaligned_accesses shows the draws reach them); qemu-aarch64: not yet run, pending the first CI run of the draft PR on ubuntu-latest (hole elf-route-unrun)

## mutants-in-import-time-tables
- Depends on it: fpl/asm/aarch64/alias.py (the alias rows and encodings built at import), mutants.allow, the ready-green law
- Default in force: 410 of 3282 fpl mutants live (1815 s wall) after scripts/mutants at 2d53cb7 (about 300 in alias.py table builders: decode_bitmask 52, same_row 42, extend_row 41, add_sub_row 39, set_row 33); none named in mutants.allow; make ready is red on the mutants lane
- Closes by: PSJ, choosing between building the tables per call (so mutmut's forked runs see the mutant), `# pragma: no mutate -- why` on table construction, or naming them in mutants.allow
- Evidence: mutants/mutmut-stats.json maps x_decode_bitmask and x_same_row to one test each; the tables are module constants (alias.py COND_SELECT), built in mutmut's parent before it forks a run per mutant, so the mutant never executes
