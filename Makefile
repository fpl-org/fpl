# The root's Makefile: the walker is a project of its own under bootstrap/, so every lane of
# the noslop gate (quality/noslop.mk) is run there, and CI's `make check` / `make ready` reach it
# from the root unchanged (.github/workflows/noslop.yml, map.yml). This file names the lanes
# and adds none: what each runs, and how hard, is quality/noslop.mk's.
#
#   make              the one gate, as `make check`
#   make <lane>       fix quick check harden ready gates tools map venv pristine clean-noslop
.DEFAULT_GOAL := check
LANES := fix quick check harden ready gates tools map venv pristine clean-noslop
.PHONY: $(LANES)

$(LANES):
	@$(MAKE) --no-print-directory -C bootstrap $@
