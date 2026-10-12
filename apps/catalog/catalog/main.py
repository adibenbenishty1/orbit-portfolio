# -*- coding: utf-8 -*-
"""

    Main entrypoint for catalog application

"""


# imports
# -------
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from catalog.config import config
from catalog.logging import api as log


# extensions
# ----------
# built before the app so the lifespan handler below can close over it, and
# attached to the app further down -- instrumentation adds middleware, which
# has to happen before the application starts serving.
prometheus = Instrumentator(
    excluded_handlers=['/metrics', '/health.*', '/ping'],
)


# lifespan
# --------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and shutdown events.

    Work here is conditional on configuration rather than on environment, so
    that one image runs everywhere and the environment decides what is on.

    Args:
        app (FastAPI) - Application being started.
    """
    log.info(f'starting {config.PROJECT} ({config.ENV})')
    app.state.started = datetime.now(timezone.utc)

    # expose metrics endpoint
    if config.PROMETHEUS_ENABLED:
        prometheus.expose(app)

    yield

    log.info(f'stopping {config.PROJECT}')


# config
# ------
app = FastAPI(
    title=config.PROJECT,
    description='Business service for orbit. Serves a list of items.',
    version=config.VERSION,
    docs_url='/docs',
    redoc_url='/redoc',
    lifespan=lifespan,
)


# middleware
# ----------
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

prometheus.instrument(
    app,
    metric_namespace=config.PROMETHEUS_NAMESPACE,
    metric_subsystem=config.PROMETHEUS_SUBSYSTEM,
)


# routers
# -------
from catalog.health import router as health  ## noqa: E402
from catalog.server.items import router as items  ## noqa: E402

app.include_router(health.router)
app.include_router(items.router)


# routes
# ------
@app.get('/ping', status_code=status.HTTP_200_OK)
async def ping():
    """
    Quick status check. Cheapest possible proof the process is answering.
    """
    return {'status': 'ok'}


@app.get('/info', status_code=status.HTTP_200_OK)
async def info():
    """
    Build metadata for the running service.

    Version and commit arrive as image build arguments, so a running pod can
    say exactly what it is.
    """
    return {
        'project': config.PROJECT,
        'env': config.ENV,
        'version': config.VERSION,
        'commit': config.COMMIT,
    }
