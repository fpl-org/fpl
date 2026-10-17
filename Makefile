# The root's Makefile: the walker is a project of its own under bootstrap/, so every lane of
# the noslop gate (quality/noslop.mk) is run there, and CI's `make check` / `make ready` reach it
# from the root unchanged (.github/workflows/noslop.yml, map.yml). This file names the lanes
# and adds none: what each runs, and how hard, is quality/noslop.mk's.
#
# It also holds the walker's entry from the root, where a README points: the package is
# bootstrap/fpl, so a bare `python -m fpl` run here does not find it. `run` and `repl` put
# bootstrap/ on the path of the one .venv's python, and the check lane runs `run` on an example
# from here (quality/noslop.mk), so the entry cannot break unnoticed.
#
#   make              the one gate, as `make check`
#   make <lane>       fix quick check harden ready gates tools map venv pristine clean-noslop
#   make run FILE=f   run the file f, a path from the root:    make run FILE=path/to/p.fpl
#   make repl ARGS=a  the REPL, with its arguments a:          make repl ARGS='-e "1 + 2"'
#   make image        the dev shell as an OCI image, ./result-oci (.agents/DEVSHELL.md)
#   make image-quick  make quick inside the loaded image, on this checkout
.DEFAULT_GOAL := check
LANES := fix quick check harden ready gates tools map venv pristine clean-noslop
.PHONY: $(LANES) run repl image image-quick

$(LANES):
	@$(MAKE) --no-print-directory -C bootstrap $@

# The walker as the root runs it: the lanes' interpreter (.venv, the root's, synced by `venv`)
# with the package, bootstrap/fpl, put on its path. A relative path means what it means from
# the root, so FILE and a REPL's --session are written from there.
FPLPY := PYTHONPATH=$(CURDIR)/bootstrap $(CURDIR)/.venv/bin/python

# The venv is prepared inside bootstrap/ with its chatter sent to stderr, so stdout is the
# program's output and nothing else: `make run` prints what `python -m fpl` prints.
VENV = @$(MAKE) --no-print-directory -C bootstrap venv >&2

run:
	$(VENV)
	@test -n "$(FILE)" || { echo "make run: name the file: make run FILE=path/to/p.fpl" >&2; exit 2; }
	@$(FPLPY) -m fpl "$(FILE)"

repl:
	$(VENV)
	@$(FPLPY) -m fpl.repl $(ARGS)

# The dev shell as an OCI image (packages.<linux system>.oci in flake.nix). dockerTools builds
# for Linux only, so on a Mac the system is the Linux one of the same architecture, and Nix
# needs a Linux builder for it. The image is a tarball: `docker load < result-oci`.
HOST_SYSTEM  ?= $(shell nix eval --impure --raw --expr builtins.currentSystem)
IMAGE_SYSTEM ?= $(subst darwin,linux,$(HOST_SYSTEM))

image:
	nix build ".#packages.$(IMAGE_SYSTEM).oci" --out-link result-oci

# make quick inside the loaded image, on this checkout, as the caller: as root one test fails.
# The tmpfs over /work/.venv gives the container a venv of its own: the host's was synced for
# the host, and its stamp would have the lanes run the host's binaries. Docker mounts a tmpfs
# root-owned and noexec, hence exec,mode=1777.
image-quick:
	docker run --rm --user "$$(id -u):$$(id -g)" -v "$(CURDIR)":/work \
	  --tmpfs /work/.venv:exec,mode=1777 fpl-dev make quick
