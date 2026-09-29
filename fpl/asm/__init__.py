"""The assembly layer: the targets FPL lowers to, each a model of its own that knows no FPL.

FPL's abstract machine A lowers to M, and M to targets such as WebAssembly (`fpl.asm.wasm`).
Nothing under `fpl.asm` imports the rest of `fpl`: the contract asm-stands-alone of
quality/importlinter.ini is the gate, and tests/test_wasm_free.py states it as a law.
"""
