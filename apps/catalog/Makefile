# ~
#
# Makefile for catalog
#
# Shares its target vocabulary with the root Makefile and with the other
# services, so the same command means the same thing everywhere.
#
# ------------------------------------------------


# config
# ------
PROJECT       := catalog
VERSION       := $(shell sed -n 's/^version *= *"\(.*\)"/\1/p' pyproject.toml | head -1)
REQUIREMENTS  := poetry docker

# every service shares the one virtualenv at the repository root, so call
# into it directly rather than through poetry, which would look for a
# virtualenv belonging to this directory alone.
VENV          := ../../.venv/bin

# the image. nested under the repository name because that is how a registry
# spells "one repository, several services", and public so that no later
# section needs a pull secret.
REGISTRY      := ghcr.io
OWNER         := adibenbenishty1
IMAGE         := $(REGISTRY)/$(OWNER)/orbit/$(PROJECT)
COMMIT        := $(shell git rev-parse --short HEAD 2>/dev/null || echo unknown)

# the build context is the repository root, not this directory: a per-service
# context cannot see the lock and metadata a path dependency needs. see the
# note in this service's Dockerfile.
# the dockerfile path is relative to this directory, while COPY paths inside
# it are relative to the context -- which is why the two look inconsistent.
CONTEXT       := ../..
DOCKERFILE    := Dockerfile

# a comma cannot be written literally inside an $(if ...) argument, so it
# arrives as a variable -- and it has to be defined before the immediate
# assignment below, which would otherwise expand it to nothing and mash the
# cache options together.
, := ,

# CACHE=gha turns on buildx's github actions cache backend, which is what CI
# sets. A local cache directory needs rotation because
# buildx cannot read and write one path in a single invocation -- this backend
# has no such conflict, so the shell choreography is replaced by one variable.
# the scope keeps the two services' caches apart in a repository building both.
CACHE         :=
CACHE_FLAGS   := $(if $(filter gha,$(CACHE)),--cache-from type=gha$(,)scope=$(PROJECT) --cache-to type=gha$(,)mode=max$(,)scope=$(PROJECT))


# targets
# -------
.PHONY: help info deps clean start test login build image push release


help: ## show this help
	@echo ""
	@$(MAKE) --no-print-directory info
	@echo ""
	@echo "Usage: make <command>"
	@echo ""
	@echo "Commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
	@echo ""


info: ## show package info
	@printf "  %-16s %s\n" "package" "$(PROJECT) $(VERSION)"
	@printf "  %-16s %s\n" "venv" "$(VENV)"
	@printf "  %-16s %s\n" "image" "$(IMAGE):$(VERSION)"
	@printf "  %-16s %s\n" "commit" "$(COMMIT)"


deps: ## check for required executables
	@for dep in $(REQUIREMENTS); do \
		printf "  \033[36m%-16s\033[0m %s\n" "$$dep" "`command -v $$dep 2>/dev/null || echo 'not found'`"; \
	done


login: ## authenticate with the image registry
	@# locally this reads a token from the gh cli; in CI the workflow's own
	@# GITHUB_TOKEN is piped in the same way, which is why §7 needs no
	@# repository secret and no auth action at all.
	gh auth token | docker login $(REGISTRY) -u $(OWNER) --password-stdin


build: ## build the python package into dist/
	@# no virtualenv of its own is wanted here, and poetry would otherwise
	@# build one in the shared cache just to package a wheel.
	POETRY_VIRTUALENVS_CREATE=false poetry build


image: ## build the container image
	@# VERSION and COMMIT cross into the image as build arguments and come
	@# back out of /info, which is how a running container says what it is.
	docker buildx build \
		--file $(DOCKERFILE) \
		--build-arg VERSION=$(VERSION) \
		--build-arg COMMIT=$(COMMIT) \
		--tag $(IMAGE):latest \
		--tag $(IMAGE):sha-$(COMMIT) \
		$(CACHE_FLAGS) \
		--load \
		$(CONTEXT)


push: image ## build and push the moving tags
	@# latest and the commit sha, which is what a push to the default branch
	@# publishes. the version tag belongs to a release and not to a branch.
	docker push $(IMAGE):latest
	docker push $(IMAGE):sha-$(COMMIT)


release: image build ## tag the built image with the version and publish both
	@# the image is re-tagged rather than rebuilt, so what is released is
	@# byte-for-byte what was tested.
	docker tag $(IMAGE):latest $(IMAGE):$(VERSION)
	docker push $(IMAGE):$(VERSION)
	docker push $(IMAGE):latest


clean: ## remove test artifacts
	rm -rf .pytest_cache dist
	find . -type d -name __pycache__ -prune -exec rm -rf {} +


start: ## serve the api
	$(VENV)/catalog serve


test: ## run tests
	$(VENV)/pytest


db-up:
	docker start orbit-postgres-local
