"""WebAssembly as a 1:1 IR: a Python mirror of Wasm modules and instructions, with no FPL in it.

The mirror follows the abstract syntax of the WebAssembly Specification, Release 3.0
(2026-07-10), pinned to the frozen PDF
<https://webassembly.github.io/spec/versions/core/WebAssembly-3.0.pdf>, sha256
6dc4a77d365a3bc4b953b1032d17617b5c10ddaf91764c57a1642427de8319b0 (its source is the tag
wg-3.0 of github.com/WebAssembly/spec). Not the living draft at /spec/core/, which moves.
Section numbers in this package are that release's.

It covers a subset: i32 and i64 only, numeric value types, function types, one memory, funcref
tables filled by active element segments, and the parametric, control (tail calls included),
variable, integer memory and integer numeric instructions. Floats, vectors, references on the
operand stack, GC types, exceptions, memory.grow, bulk memory, memory64 and multi-memory are
out of the model (HOLES.md: gc-and-exceptions).

    types   spec 2.3, the types
    instr   spec 2.4, the instructions
    module  spec 2.5, the module and its fields
    text    spec 6, the printer to WAT
"""
