"""The oracles of fpl.asm.wasm: pinned, resolved once, and able to fail."""

import pytest
from hypothesis import given
from hypothesis import strategies as st
from wasm_oracle import RESOLVE, STORE, VERSIONS, OracleError, Tools, resolve, store_paths, versions

store_lines = st.text(alphabet="abc0123456789-./", min_size=1).map(lambda rest: STORE + rest)
other_lines = st.sampled_from(["", "==> wiring the git hooks", "wat2wasm", " /nix/store/x"])


@given(st.lists(store_lines | other_lines, max_size=4))
def test_the_oracles_are_the_pinned_store_paths(wasm_tools: Tools, lines: list[str]) -> None:
    """[law: oracle-pinned] Resolution takes exactly one /nix/store/ line per tool, no more.

    The fixture resolved wabt 1.0.41 and wasmtime 45.0.2 from the worktree's own wasm layer;
    every binary it hands out is an absolute path into the store; and of any stdout the resolving
    command could print, only exactly two /nix/store/ lines are accepted.
    """
    exact = len(lines) == 2 and all(line.startswith(STORE) for line in lines)
    assert (store_paths("".join(line + "\n" for line in lines)) is not None) == exact
    every = (
        wasm_tools.wat2wasm,
        wasm_tools.wast2json,
        wasm_tools.spectest_interp,
        wasm_tools.wasm_validate,
        wasm_tools.wasmtime,
    )
    assert all(path.is_absolute() and str(path).startswith(STORE) for path in every)
    assert versions(wasm_tools) == VERSIONS


def test_without_nix_resolving_is_an_error() -> None:
    with pytest.raises(OracleError, match="/nonexistent/nix develop"):
        resolve(RESOLVE.replace("nix develop", "/nonexistent/nix develop", 1))
