# Holes

Undecided choices of the wasm-ir track, each with the default in force until someone closes it.

## gc-and-exceptions
- Depends on it: fpl/asm/wasm/types.py (FuncType is the only type definition), fpl/asm/wasm/instr.py (no reference, aggregate or exception instructions), the checker of later units, the D track's lowering of Fail and escalation
- Default in force: excluded: every type definition is a singleton, final, non-recursive function type; no tags, no throw, throw_ref or try_table, no reference values on the operand stack; a Wasm trap is a root panic (row 43), never FPL's Fail, which lowers to ordinary control transfer to a supervisor continuation (row 81)
- Closes by: PSJ with palimpsest, deciding C2's reclamation (row 80); row 81 recommends linear memory with own reference counting, WasmGC only as a later second model of M's allocation operations
- Evidence: backend-plan.md prompt B ("GC types and exceptions are one named hole"); row 81 (3); WebAssembly 3.0 sections 2.3.4, 2.3.9-2.3.10, 2.3.13, 2.4.2, 2.4.7, 2.5.3; track design section 9

## crosshair-literal
- Depends on it: fpl/asm/wasm/instr.py (Const guards its range in `__post_init__`), tests/test_wasm_instr.py, every later contract over a Literal-typed field (design's Cvtop contract on `to` and `source`), the law contracts-hold
- Default in force: a class with a Literal-typed field guards its invariant in `__post_init__` with ValueError, through a named typed predicate (`const_in_range`), not with `icontract.invariant`; CrossHair then has no contract to analyse there, so the symbolic check of that predicate is lost while the runtime refusal and its Hypothesis tests stay
- Closes by: the maintainer, bumping crosshair-tool in quality/ to a version that proxies `typing.Literal` (upstream issue: the crash should be CrosshairUnsupported, and a Literal can be chosen by `smt_fork` like the Enum branch beside it), then moving the guards back to `icontract.invariant`
- Evidence: .venv/lib/python3.12/site-packages/crosshair/core.py:558-570 (proxy_for_class calls get_type_hints on `Literal[...]` and catches only AttributeError and NameError) and :811 (`_SIMPLE_PROXIES` has no Literal); a PEP 695 `type` alias crashes in dynamic_typing.realize instead; design section 3 (operator names are Literal strings, not enums; Const's range; Cvtop's contract)
