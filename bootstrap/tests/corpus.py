"""Where the maintainer's examples are: the conformance suite, features/ at the top of the
repository, above this project. Tests find it by walking up from here, so they find it from
this directory and from mutmut's copy of it (mutants/), and a repository without one fails
the run loudly instead of testing an empty corpus."""

from pathlib import Path


def repository() -> Path:
    """The nearest directory above this file that holds features/."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "features").is_dir():
            return parent
    msg = "no features/ above tests/: the conformance suite is missing"
    raise FileNotFoundError(msg)


REPO = repository()
PROGRAMS = sorted(REPO.glob("features/*/examples/*.fpl"))
if not PROGRAMS:
    raise FileNotFoundError(f"no example programs under {REPO / 'features'}")
