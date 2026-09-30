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
- Evidence: design.md section 7, probe: ten fresh links 126-300 ms, the same binary rerun 2 ms
