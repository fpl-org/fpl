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

## oracle-feature-set
- Depends on it: fpl/asm/wasm/valid.py (constant expressions, block types, typed select), tests/wasm_oracle.py (flags), tests/test_wasm_valid.py (the SPEC_ONLY cases), tests/wasm_strategies.py (const_exprs, the catalogue's type mutation)
- Default in force: the oracles run at their defaults plus wabt's --enable-tail-call; every constant expression is one t.const or global.get of an imported immutable global, and there is one memory, where wabt 1.0.41, wasmtime 45.0.2 and Release 3.0 agree. Where wabt leaves 3.0 (it accepts a block type index out of range and a typed select with no type, both refused by wasmtime), the checker follows 3.0, those cases stay fixed tests off the oracles, and the catalogue's type mutation raises a function's type index instead of a block's
- Closes by: the implementer of a later track that needs extended constants or multi-memory, adding the wabt flags and re-probing wasmtime; the two wabt divergences by an upstream wabt issue, then moving the SPEC_ONLY cases to AGREED
- Evidence: design sections 0 (probe cexpr.wast) and 9; spec 3.0 3.2.8, 3.4.1, 3.4.13, 7.8; this unit's smoke of each invalid family through both engines (block type index and empty typed select: wabt valid, wasmtime invalid)

## exhaustion-outcome
- Depends on it: fpl/asm/wasm/exec.py (Exhausted, DEPTH), tests/test_wasm_exec.py, the D track's lowering of non-tail recursion
- Default in force: the evaluator stops at a call depth of 64 active calls with Exhausted, never compared with an engine; tail calls loop in the call driver and never count; generated runnable programs cannot reach it (fuel), and the type-soundness property keeps its step budget below 64 so no run can
- Closes by: palimpsest, saying whether stack exhaustion is a root panic like a trap (row 43) or something the lowering must rule out
- Evidence: design section 6 and section 9 exhaustion-outcome; spec 3.0 7.3.3 (the number of frames is an implementation limit); row 81 (1) names stack exhaustion among the sources of nondeterminism

## bulk-memory
- Depends on it: fpl/asm/wasm/instr.py (no memory.fill, memory.copy, memory.init or data.drop), fpl/asm/wasm/module.py (Data and Elem are active only)
- Default in force: excluded: memory.fill, memory.copy, memory.init, data.drop, and passive and declarative segments are outside the subset; the checker, printer and evaluator have no case for them
- Closes by: the D track, if stackify or the bump heap wants memory.fill or memory.copy; a model addition with its checker rule, printer line and evaluator case
- Evidence: design section 9 bulk-memory; spec 3.0 2.4.5, 2.5.8, 2.5.9; prompt B's subset does not list them

## python-stack-bound
- Depends on it: fpl/asm/wasm/exec.py (DEPTH, the big-step evaluator), tests/test_wasm_exec.py (the exhaustion test recurses with no block), the laws type-soundness and evaluator-agrees under mutmut
- Default in force: DEPTH stays 64 active calls, but each block around a call adds Python frames, so DEPTH does not always fire before Python's recursion limit of 1000; the fixed exhaustion test recurses with no block, and generated runnable programs stay within fuel 32 and block depth 4
- Closes by: Manicule on the design side, choosing a lower DEPTH, a DEPTH that counts block nesting, or the iterative evaluator that design section 11 names as the fallback; then the exhaustion test may nest blocks again
- Evidence: design section 6 ("set at a call depth of 64 so that it always fires before Python's own recursion limit") and section 11; measured in unit 7 by raising sys.setrecursionlimit until a self-call wrapped in n blocks reaches Exhausted: natively n=0 200, n=1 350, n=2 500, n=4 750 frames; in mutmut's mutants/ copy (trampoline) n=0 600, n=1 1000, n=2 1400, n=4 2150, so the old 4-block test failed mutmut's clean run with RecursionError
