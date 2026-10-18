"""
Diff one example through the in-process run and the FON pipe against the
seed walker.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
EXAMPLE = REPO / "03-fpl/03.01-features/draft2/examples/01-frames.fpl"
PYTHON = os.environ.get("FPL_PYTHON", sys.executable)
BIN = ROOT / "bin" / "fpl"


def run(
    args: list[str], env: dict[str, str], stdin: bytes | None = None
) -> bytes:
    result = subprocess.run(
        args, input=stdin, capture_output=True, env=env, check=False
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr.decode() or result.stdout.decode())
    return result.stdout


def main() -> None:
    subprocess.run([PYTHON, str(ROOT / "tangle.py")], check=True)
    env = os.environ.copy()
    env["FPL_PYTHON"] = PYTHON
    env["PYTHONPATH"] = f"{ROOT / 'python'}{os.pathsep}{ROOT / '.vendor'}"
    ours = run([str(BIN), str(EXAMPLE)], env)
    seed_env = env.copy()
    seed_env["PYTHONPATH"] = str(ROOT)
    seed = run([PYTHON, "-m", "fpl", str(EXAMPLE)], seed_env)
    if ours != seed:
        raise SystemExit("in-process run differs from the seed walker")
    data = EXAMPLE.read_bytes()
    for stage in (
        "source",
        "lex",
        "parse",
        "desugar",
        "elaborate",
        "eval",
        "render",
    ):
        data = run([str(BIN), stage], env, data)
    if data != seed:
        raise SystemExit("pipe differs from the seed walker")
    print("matched", EXAMPLE.name)


if __name__ == "__main__":
    main()
