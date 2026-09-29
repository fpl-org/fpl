# Holes

Undecided choices of the wasm-ir track, each with the default in force until someone closes it.

## gc-and-exceptions
- Depends on it: fpl/asm/wasm/types.py (FuncType is the only type definition), fpl/asm/wasm/instr.py (no reference, aggregate or exception instructions), the checker of later units, the D track's lowering of Fail and escalation
- Default in force: excluded: every type definition is a singleton, final, non-recursive function type; no tags, no throw, throw_ref or try_table, no reference values on the operand stack; a Wasm trap is a root panic (row 43), never FPL's Fail, which lowers to ordinary control transfer to a supervisor continuation (row 81)
- Closes by: PSJ with palimpsest, deciding C2's reclamation (row 80); row 81 recommends linear memory with own reference counting, WasmGC only as a later second model of M's allocation operations
- Evidence: backend-plan.md prompt B ("GC types and exceptions are one named hole"); row 81 (3); WebAssembly 3.0 sections 2.3.4, 2.3.9-2.3.10, 2.3.13, 2.4.2, 2.4.7, 2.5.3; track design section 9
