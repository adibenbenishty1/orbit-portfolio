# ~
#
# Image for catalog
#
# Two-stage. The builder resolves dependencies into a virtualenv at a fixed
# path and installs the service into it; the runtime stage copies that one
# directory across and nothing else, so the build toolchain never ships.
#
# Built with the repository root as build context, not this directory:
#
#     docker build -f apps/catalog/Dockerfile -t orbit/catalog .
#
# ------------------------------------------------


# builder
# -------
FROM python:3.13-slim AS builder

# poetry is installed into the system python, before the service virtualenv
# exists, so that its own dependencies can never collide with the service's.
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=2.3.2 \
    POETRY_VIRTUALENVS_CREATE=false

RUN pip install "poetry==${POETRY_VERSION}"

# the virtualenv path is fixed and known, which is what lets the runtime
# stage copy it by name. VIRTUAL_ENV is what poetry reads to decide where to
# install, given it has been told not to create an environment of its own.
ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:${PATH}"

RUN python -m venv "${VIRTUAL_ENV}"

WORKDIR /src

# lockfile and metadata first, source second. dependencies change rarely and
# source changes constantly, so this ordering is what keeps the dependency
# layer alive across an edit -- the largest build-time win available here.
#
# the lockfile is this service's own rather than the repository root's. the
# root lock covers both services as path dependencies, so installing from it
# would put catalog inside gate's image and gate inside catalog's. see the
# note in the root Makefile.
COPY apps/catalog/pyproject.toml apps/catalog/poetry.lock ./
RUN poetry install --only main --no-root

# the project itself, installed non-editable: the runtime stage receives a
# real package in site-packages rather than a link into a source tree that
# will not be copied.
COPY apps/catalog/catalog ./catalog
RUN pip install --no-deps .


# runtime
# -------
FROM python:3.13-slim AS runtime

# version and commit arrive as build arguments and are re-exported below, so
# that /info can say exactly which build is answering. both default to the
# same 'unknown' the config declares, so an un-argued build is honest rather
# than wrong.
ARG VERSION=unknown
ARG COMMIT=unknown

ENV VERSION=${VERSION} \
    COMMIT=${COMMIT} \
    CONTAINER=true \
    PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=builder /opt/venv /opt/venv

# an unprivileged user, because nothing here writes anything. the home
# directory is the working directory so that a stray relative path lands
# somewhere the process can actually use.
RUN useradd --create-home --uid 1000 orbit
USER orbit
WORKDIR /home/orbit

COPY --chown=orbit:orbit apps/catalog/alembic.ini ./alembic.ini
COPY --chown=orbit:orbit apps/catalog/alembic ./alembic

# documentation rather than mechanism -- publishing a port is the run's
# decision, and in orbit's compose file catalog deliberately publishes none.
EXPOSE 5000

CMD ["catalog", "serve"]
