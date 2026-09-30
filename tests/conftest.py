"""Session fixtures: the oracles of fpl.asm.wasm, resolved once per test process."""

import pytest
from wasm_oracle import Tools, pinned


@pytest.fixture(scope="session")
def wasm_tools() -> Tools:
    """wabt and wasmtime from the worktree's own wasm layer (tests/wasm_oracle.py)."""
    return pinned()
