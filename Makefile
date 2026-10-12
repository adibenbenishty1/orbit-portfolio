# ~
#
# Makefile for orbit
#
# Dispatches into the services under apps/. Each service has its own
# Makefile sharing this target vocabulary, so `make <target>` means the
# same thing wherever it is run.
#
# ------------------------------------------------


# config
# ------
PROJECT       := orbit
APPS          := $(notdir $(wildcard apps/*))
REQUIREMENTS  := poetry docker make helm kubectl gh

# the registry, repeated here rather than reached for. each service Makefile
# carries these same two lines, which is the one duplication in the shared
# vocabulary and a deliberate one: a Makefile that needs another Makefile's
# variables is a Makefile that cannot be run on its own, and being runnable
# from any directory is the point of the vocabulary.
REGISTRY      := ghcr.io
OWNER         := adibenbenishty1


# targets
# -------
.PHONY: help info deps lock install clean test login image push release


help: ## show this help
	@echo ""
	@$(MAKE) --no-print-directory info
	@echo ""
	@echo "Usage: make <command>"
	@echo ""
	@echo "Commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Apps:"
	@for app in $(APPS); do \
		printf "  \033[36m%-16s\033[0m %s\n" "$$app" "make -C apps/$$app help"; \
	done
	@echo ""
	@echo "Requirements:"
	@$(MAKE) --no-print-directory deps
	@echo ""


info: ## show project info
	@echo "$(PROJECT)"
	@printf "  %-16s %s\n" "apps" "$(if $(APPS),$(APPS),none yet)"
	@printf "  %-16s %s\n" "last update" "`git log -1 --format=%cd --date=short 2>/dev/null || echo unknown`"


deps: ## check for required executables
	@for dep in $(REQUIREMENTS); do \
		printf "  \033[36m%-16s\033[0m %s\n" "$$dep" "`command -v $$dep 2>/dev/null || echo 'not found'`"; \
	done


# there are three lock files, and they are refreshed together on purpose.
#
# the root lock is what `poetry install` builds the one virtualenv from, and
# it covers every service as a path dependency. each service also carries its
# own lock, because an image must install that service's dependencies and no
# others -- installing from the root lock would put catalog inside gate's
# image and gate inside catalog's, which would make catalog's own description
# of itself as the service containing no security code untrue.
#
# the cost is drift: three resolutions of the same constraints could disagree,
# and the tests would then be run against versions the images do not have.
# refreshing all three in one target is what bounds it, so refresh them that
# way rather than running poetry by hand in one directory.
lock: ## refresh every lock file after changing dependencies
	poetry lock --no-update
	@# a service directory has no virtualenv of its own and wants none --
	@# poetry would otherwise build one in the shared cache just to resolve.
	@for app in $(APPS); do \
		(cd apps/$$app && POETRY_VIRTUALENVS_CREATE=false poetry lock --no-update); \
	done


# poetry only hashes the root pyproject, so a change to a service's
# dependencies leaves the lock stale and `poetry check --lock` still passes.
# make tracks it by mtime instead.
poetry.lock: pyproject.toml $(wildcard apps/*/pyproject.toml)
	@$(MAKE) --no-print-directory lock


install: poetry.lock ## install all services and dev tooling into one virtualenv
	poetry install
	@# poetry does not notice metadata changes inside an editable path
	@# dependency, so a new console script or entry point never appears.
	@# redoing the editable installs is cheap, since deps are already resolved.
	@for app in $(APPS); do \
		poetry run pip install -q --disable-pip-version-check -e apps/$$app --no-deps; \
	done


test: ## run tests for every service
	@for app in $(APPS); do \
		$(MAKE) --no-print-directory -C apps/$$app test || exit 1; \
	done


# one login covers every image in the registry, so this one does not dispatch.
login: ## authenticate with the image registry
	gh auth token | docker login $(REGISTRY) -u $(OWNER) --password-stdin


# the build half of the vocabulary, dispatched the same way tests are. CI
# never calls these -- a workflow is path-filtered to one service and calls
# that service's target directly, which is the whole reason for the filters.
image: ## build the image for every service
	@for app in $(APPS); do \
		$(MAKE) --no-print-directory -C apps/$$app image || exit 1; \
	done


push: ## build and push the moving tags for every service
	@for app in $(APPS); do \
		$(MAKE) --no-print-directory -C apps/$$app push || exit 1; \
	done


release: ## publish the versioned image and package for every service
	@for app in $(APPS); do \
		$(MAKE) --no-print-directory -C apps/$$app release || exit 1; \
	done


clean: ## remove build and test artifacts
	rm -rf dist apps/*/dist
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
