"""quality/noslop_pytest.py — the pytest plugin every implementation worktree loads.

Hypothesis profiles, chosen with HYPOTHESIS_PROFILE: `quick` for the inner loop and `make
check`; `harden` for `make harden`, which searches far longer for a counterexample; and
`symbolic`, also in `make harden`, which hands the same properties to CrossHair: instead of
drawing random inputs it solves for inputs that reach each branch, so it finds the one value
in a billion that random search does not. Kept in the harness so an attempt cannot quietly
shrink how hard its properties are searched.
"""

import os

from hypothesis import HealthCheck, settings

settings.register_profile("quick", max_examples=100, deadline=None)
settings.register_profile(
    "harden",
    max_examples=2000,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.register_profile(
    "symbolic",
    backend="crosshair",
    max_examples=50,
    deadline=None,
    suppress_health_check=list(HealthCheck),
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "quick"))
