# quality/noslop.mk — the noslop harness's lanes. A project's Makefile is one line, `include
# ../quality/noslop.mk` (bootstrap/Makefile); everything the gate runs, and how hard, lives
# here, in the root's shared harness, so a project cannot loosen its own gate
# (.agents/QUALITY.md). The lanes run in the project's directory, bootstrap/, a child of the
# root; the harness's quality/ and scripts/ and the one .venv are the root's. The root's
# Makefile runs each lane there, and `make -f quality/noslop.mk gates` runs at the root.
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
#                 Reached only by name, so no other lane waits on it
#   make map      the map of the code, imports and classes, drawn into .noslop/map/ and never
#                 committed; no other lane runs it (scripts/diagrams)

.DEFAULT_GOAL := check
.PHONY: fix quick check harden ready gates tools map venv pristine clean-noslop

# The root is where this file's directory sits one level down. It is read before anything
# else is included, so it is this file's, wherever make runs and whatever includes it.
ROOT     := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))..)
Q        := $(ROOT)/quality
S        := $(ROOT)/scripts
VENV     := $(ROOT)/.venv
BIN      := $(VENV)/bin
# What the lanes leave behind, in the directory they run in (the root's .gitignore covers it).
OUT      := .noslop
# CPU seconds CrossHair spends looking for a counterexample to one contract (make harden).
CONTRACT_SECONDS := 20
export PYTHONPATH := $(Q):$(CURDIR)
export UV_PROJECT_ENVIRONMENT := $(VENV)
export UV_PYTHON_DOWNLOADS := never

# ruff skips what a VCS ignore file hides, and a clone whose .git/info/exclude is block-first
# (`*`) hides every source: ruff then lints nothing and passes. The lanes name their files, so
# it is told to look at them whatever the ignore files say.
RUFF_ALL := --no-respect-gitignore

# The tools, at the versions quality/uv.lock pins, synced into the root's .venv. The stamp
# makes it a no-op until the lock changes.
$(BIN)/.synced: $(Q)/uv.lock $(Q)/pyproject.toml
	uv sync --project $(Q) --frozen --python python3.12 --quiet
	@touch $@
venv: $(BIN)/.synced

fix: venv
	$(BIN)/ruff check --config $(Q)/ruff.toml $(RUFF_ALL) --fix fpl tests
	$(BIN)/ruff format --config $(Q)/ruff.toml $(RUFF_ALL) fpl tests

quick: venv
	$(BIN)/ruff check --config $(Q)/ruff.toml $(RUFF_ALL) fpl tests
	$(BIN)/ruff format --config $(Q)/ruff.toml $(RUFF_ALL) --check fpl tests
	$(BIN)/pytest -x -q -n auto

# A gate is only as strict as its policy files, and those sit in the worktree where an
# edit is one keystroke away. So the gate runs only against the committed policy: an
# uncommitted change to any of them stops it. Commit such a change first, with [policy].
# The project's own are named from the root, as the directory these lanes run in.
WALKER := $(notdir $(CURDIR))
POLICY := quality scripts Makefile $(addprefix $(WALKER)/,Makefile pyproject.toml mutants.allow)
pristine:
	@dirty="$$(git -C $(ROOT) status --porcelain --untracked-files=all -- $(POLICY))" || { \
	  echo "pristine: git could not read the policy files' state, so the gate does not run;" >&2; \
	  echo "          run 'git -C $(ROOT) status -- $(POLICY)' to see why" >&2; \
	  exit 1; \
	}; \
	if [ -n "$$dirty" ]; then \
	  echo "check: the gate's policy files differ from what is committed:" >&2; \
	  echo "$$dirty" | sed 's/^/         /' >&2; \
	  echo "       the gate judges only committed policy; commit the change with [policy]," >&2; \
	  echo "       in a harness commit for quality/ and scripts/ (.agents/WORKTREES.md)" >&2; \
	  exit 1; \
	fi

check: venv pristine
	@mkdir -p $(OUT)
	$(BIN)/ruff check --config $(Q)/ruff.toml $(RUFF_ALL) fpl tests
	$(BIN)/ruff format --config $(Q)/ruff.toml $(RUFF_ALL) --check fpl tests
	pyright --project $(Q)/pyright.json
	$(BIN)/mypy --config-file $(Q)/mypy.ini fpl tests
	$(BIN)/python $(S)/escapes fpl tests
	$(BIN)/python $(S)/props --obligations $(Q)/obligations.toml
	$(BIN)/coverage erase --rcfile=$(Q)/coveragerc
	$(BIN)/coverage run --rcfile=$(Q)/coveragerc -m pytest -q
	$(BIN)/coverage json --rcfile=$(Q)/coveragerc -q --fail-under=0
	$(BIN)/python $(S)/crap --policy $(Q)/crap.toml
	$(BIN)/coverage report --rcfile=$(Q)/coveragerc
	$(BIN)/lint-imports --config $(Q)/importlinter.ini --no-cache
	@! $(BIN)/deptry . --extend-exclude 'mutants' -v 2>&1 | grep -q '^Scanning 0 file' || { \
	  echo "check: deptry scanned 0 files: a VCS ignore file (.gitignore, .git/info/exclude) hides the sources" >&2; \
	  echo "       from it, and deptry has no switch to look anyway; allow fpl/ and tests/ there" >&2; \
	  exit 1; }
	$(BIN)/deptry . --extend-exclude 'mutants'
	$(BIN)/vulture fpl tests --min-confidence 60
	$(BIN)/pylint --rcfile=/dev/null --persistent=n --score=n --disable=all --enable=duplicate-code \
	  --min-similarity-lines=6 --ignore-imports=yes --ignore-signatures=yes fpl

harden: check
	@$(BIN)/python -c 'import z3' 2>/dev/null || { echo 'harden: z3 does not load, so CrossHair cannot run;' \
	  'on Linux the dev shell puts libstdc++ on LD_LIBRARY_PATH (.agents/DEVSHELL.md)' >&2; exit 1; }
	HYPOTHESIS_PROFILE=harden $(BIN)/pytest -q -n auto
	HYPOTHESIS_PROFILE=symbolic $(BIN)/pytest -q -n auto
	$(BIN)/crosshair check fpl --analysis_kind=icontract --per_condition_timeout=$(CONTRACT_SECONDS)
	$(BIN)/python $(S)/mutants

ready: harden gates
	@mkdir -p $(OUT)
	uv export --project $(Q) --frozen --quiet > $(OUT)/requirements.txt
	$(BIN)/pip-audit --progress-spinner off --requirement $(OUT)/requirements.txt --disable-pip

# The harness's own Python, judged by the same ruff it judges others with.
HARNESS := $(addprefix $(S)/,crap props escapes mutants gates forward-only diagrams) \
           $(Q)/noslop_pytest.py

gates: venv
	$(BIN)/ruff check --config $(Q)/ruff.toml $(HARNESS)
	$(BIN)/ruff format --config $(Q)/ruff.toml --check $(HARNESS)
	$(BIN)/python $(S)/crap --self-test
	$(BIN)/python $(S)/props --self-test
	$(BIN)/python $(S)/escapes --self-test
	$(BIN)/python $(S)/forward-only --self-test
	$(BIN)/python $(S)/mutants --self-test
	$(BIN)/python $(S)/diagrams --self-test
	$(S)/leak-check --self-test
	$(S)/pre-push-self-test
	$(S)/boundary-self-test
	$(BIN)/python $(S)/gates

# Each tool syncs its own locked environment into <tool>/.venv, so its dependencies never
# enter the language's. The package a tool ships is named after its directory. escapes is
# handed the package and the tests, never the tool's root, which holds the .venv.
TOOLS := $(patsubst %/pyproject.toml,%,$(wildcard $(ROOT)/tools/*/pyproject.toml))

tools: venv
	$(BIN)/ruff check --config $(Q)/ruff.toml $(ROOT)/tools
	$(BIN)/ruff format --config $(Q)/ruff.toml --check $(ROOT)/tools
	@set -ex; for t in $(TOOLS); do \
	  p=$$(basename $$t); \
	  UV_PROJECT_ENVIRONMENT=$$t/.venv uv sync --project $$t --frozen --all-extras \
	    --python python3.12 --quiet; \
	  pyright --project $$t/pyright.json; \
	  (cd $$t && .venv/bin/mypy --config-file $(Q)/mypy.ini $$p tests); \
	  $(BIN)/python $(S)/escapes $$t/$$p $$t/tests; \
	  mkdir -p $$t/.noslop; \
	  (cd $$t && .venv/bin/coverage erase --rcfile=coveragerc \
	    && .venv/bin/coverage run --rcfile=coveragerc -m pytest -q \
	    && .venv/bin/coverage report --rcfile=coveragerc); \
	done

# A view of the code, not a check: computed from the code each time, so it cannot go stale,
# and kept out of git, where it would. .github/workflows/map.yml draws it on every PR. It is
# drawn from the root, where scripts/diagrams finds the package under its SOURCE, into the
# root's .noslop/map, where that workflow reads it.
map: venv
	$(BIN)/python $(S)/diagrams --root $(ROOT) --out $(ROOT)/.noslop/map

clean-noslop:
	rm -rf $(OUT) $(ROOT)/.noslop/map mutants .hypothesis .import_linter_cache
