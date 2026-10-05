# quality/noslop.mk — the noslop harness's lanes. An implementation worktree's Makefile is
# one line, `include quality/noslop.mk`; everything the gate runs, and how hard, lives here,
# in the root's shared harness, so an attempt cannot loosen its own gate (docs/QUALITY.md).
#
#   make fix      rewrite what can be rewritten: ruff's safe fixes, then the formatter
#   make quick    the inner loop, seconds: lint, format, and the tests, stopping at the first
#   make check    the one gate; green here means done (AGENTS.md)
#   make harden   the long search: 20x the examples, CrossHair on every property and every
#                 contract, mutants
#   make ready    check + harden + gates + a known-vulnerability audit; before a PR leaves draft
#   make gates    proof that each check still bites: the harness's own lint, its self-tests,
#                 and a bad example each check refuses. Also what the root runs, where there
#                 is no code to judge: make -f quality/noslop.mk gates
#   make tools    the tooling beside the language: every tools/<name>/ that holds a
#                 pyproject.toml, a uv project of its own, judged as strictly as the code.
#                 Reached only by name, so no other lane waits on it; from the root:
#                 make -f quality/noslop.mk tools
#   make map      the map of the code, imports and classes, drawn into .noslop/map/ and never
#                 committed; no other lane runs it (scripts/diagrams)

.DEFAULT_GOAL := check
.PHONY: fix quick check harden ready gates tools map venv pristine clean-noslop

Q        := quality
VENV     := .venv
BIN      := $(VENV)/bin
OUT      := .noslop
# CPU seconds CrossHair spends looking for a counterexample to one contract (make harden).
CONTRACT_SECONDS := 20
export PYTHONPATH := $(CURDIR)/$(Q):$(CURDIR)
export UV_PROJECT_ENVIRONMENT := $(CURDIR)/$(VENV)
export UV_PYTHON_DOWNLOADS := never

# The tools, at the versions quality/uv.lock pins, synced into this worktree's .venv. The
# stamp makes it a no-op until the lock changes.
$(BIN)/.synced: $(Q)/uv.lock $(Q)/pyproject.toml
	uv sync --project $(Q) --frozen --python python3.12 --quiet
	@touch $@
venv: $(BIN)/.synced

fix: venv
	$(BIN)/ruff check --config $(Q)/ruff.toml --fix fpl tests
	$(BIN)/ruff format --config $(Q)/ruff.toml fpl tests

quick: venv
	$(BIN)/ruff check --config $(Q)/ruff.toml fpl tests
	$(BIN)/ruff format --config $(Q)/ruff.toml --check fpl tests
	$(BIN)/pytest -x -q -n auto

# A gate is only as strict as its policy files, and those sit in the worktree where an
# edit is one keystroke away. So the gate runs only against the committed policy: an
# uncommitted change to any of them stops it. Commit such a change first, with [policy].
POLICY := quality scripts Makefile pyproject.toml mutants.allow
pristine:
	@dirty="$$(git status --porcelain --untracked-files=all -- $(POLICY))"; \
	if [ -n "$$dirty" ]; then \
	  echo "check: the gate's policy files differ from what is committed:" >&2; \
	  echo "$$dirty" | sed 's/^/         /' >&2; \
	  echo "       the gate judges only committed policy; commit the change with [policy]," >&2; \
	  echo "       from the root for quality/ and scripts/ (docs/QUALITY.md)" >&2; \
	  exit 1; \
	fi

check: venv pristine
	@mkdir -p $(OUT)
	$(BIN)/ruff check --config $(Q)/ruff.toml fpl tests
	$(BIN)/ruff format --config $(Q)/ruff.toml --check fpl tests
	pyright --project $(Q)/pyright.json
	$(BIN)/mypy --config-file $(Q)/mypy.ini fpl tests
	$(BIN)/python scripts/escapes fpl tests
	$(BIN)/python scripts/props
	$(BIN)/coverage erase --rcfile=$(Q)/coveragerc
	$(BIN)/coverage run --rcfile=$(Q)/coveragerc -m pytest -q
	$(BIN)/coverage json --rcfile=$(Q)/coveragerc -q --fail-under=0
	$(BIN)/python scripts/crap
	$(BIN)/coverage report --rcfile=$(Q)/coveragerc
	$(BIN)/lint-imports --config $(Q)/importlinter.ini --no-cache
	$(BIN)/deptry . --extend-exclude 'mutants|quality|scripts|tools'
	$(BIN)/vulture fpl tests --min-confidence 60
	$(BIN)/pylint --rcfile=/dev/null --persistent=n --score=n --disable=all --enable=duplicate-code \
	  --min-similarity-lines=6 --ignore-imports=yes --ignore-signatures=yes fpl

harden: check
	@$(BIN)/python -c 'import z3' 2>/dev/null || { echo 'harden: z3 does not load, so CrossHair cannot run;' \
	  'on Linux the dev shell puts libstdc++ on LD_LIBRARY_PATH (docs/DEVSHELL.md)' >&2; exit 1; }
	HYPOTHESIS_PROFILE=harden $(BIN)/pytest -q -n auto
	HYPOTHESIS_PROFILE=symbolic $(BIN)/pytest -q -n auto
	$(BIN)/crosshair check fpl --analysis_kind=icontract --per_condition_timeout=$(CONTRACT_SECONDS)
	$(BIN)/python scripts/mutants

ready: harden gates
	@mkdir -p $(OUT)
	uv export --project $(Q) --frozen --quiet > $(OUT)/requirements.txt
	$(BIN)/pip-audit --progress-spinner off --requirement $(OUT)/requirements.txt --disable-pip

# The harness's own Python, judged by the same ruff it judges others with.
HARNESS := scripts/crap scripts/props scripts/escapes scripts/mutants scripts/gates \
           scripts/forward-only scripts/diagrams $(Q)/noslop_pytest.py

gates: venv
	$(BIN)/ruff check --config $(Q)/ruff.toml $(HARNESS)
	$(BIN)/ruff format --config $(Q)/ruff.toml --check $(HARNESS)
	$(BIN)/python scripts/crap --self-test
	$(BIN)/python scripts/props --self-test
	$(BIN)/python scripts/escapes --self-test
	$(BIN)/python scripts/forward-only --self-test
	$(BIN)/python scripts/mutants --self-test
	$(BIN)/python scripts/diagrams --self-test
	scripts/leak-check --self-test
	scripts/pre-push-self-test
	$(BIN)/python scripts/gates

# Each tool syncs its own locked environment into <tool>/.venv, so its dependencies never
# enter the language's. The package a tool ships is named after its directory. escapes is
# handed the package and the tests, never the tool's root, which holds the .venv.
TOOLS := $(patsubst %/pyproject.toml,%,$(wildcard tools/*/pyproject.toml))

tools: venv
	$(BIN)/ruff check --config $(Q)/ruff.toml tools
	$(BIN)/ruff format --config $(Q)/ruff.toml --check tools
	@set -ex; for t in $(TOOLS); do \
	  p=$$(basename $$t); \
	  UV_PROJECT_ENVIRONMENT=$(CURDIR)/$$t/.venv uv sync --project $$t --frozen --all-extras \
	    --python python3.12 --quiet; \
	  pyright --project $$t/pyright.json; \
	  (cd $$t && .venv/bin/mypy --config-file $(CURDIR)/$(Q)/mypy.ini $$p tests); \
	  $(BIN)/python scripts/escapes $$t/$$p $$t/tests; \
	  mkdir -p $$t/.noslop; \
	  (cd $$t && .venv/bin/coverage erase --rcfile=coveragerc \
	    && .venv/bin/coverage run --rcfile=coveragerc -m pytest -q \
	    && .venv/bin/coverage report --rcfile=coveragerc); \
	done

# A view of the code, not a check: computed from the code each time, so it cannot go stale,
# and kept out of git, where it would. .github/workflows/map.yml draws it on every PR.
map: venv
	$(BIN)/python scripts/diagrams --out $(OUT)/map

clean-noslop:
	rm -rf $(OUT) mutants .hypothesis .import_linter_cache
