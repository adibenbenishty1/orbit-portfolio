# -*- coding: utf-8 -*-
"""

    Health API

"""


# imports
# -------
from datetime import datetime, timezone

from fastapi import APIRouter, Request, status

from gate.config import config


# router
# ------
router = APIRouter(
    prefix='/health',
    tags=['health'],
    responses={404: {'description': 'Not found'}},
)


# endpoints
# ---------
@router.get('', status_code=status.HTTP_200_OK)
async def health(request: Request):
    """
    Detailed health for monitoring and for the cli status command.

    Args:
        request (Request) - Incoming request, used to read application state.
    """
    started = getattr(request.app.state, 'started', None)
    uptime = (datetime.now(timezone.utc) - started).total_seconds() if started else 0

    return {
        'status': 'up',
        'env': config.ENV,
        'started': started,
        'uptime': uptime,
    }


@router.get('/alive', status_code=status.HTTP_200_OK)
async def alive():
    """
    Liveness probe. Answers for as long as the process is serving requests.

    Kept free of dependency checks on purpose: a failing liveness probe gets
    the container restarted, which cannot fix a broken dependency.
    """
    return {'status': 'alive'}


@router.get('/ready', status_code=status.HTTP_200_OK)
async def ready():
    """
    Readiness probe. Answers when the service can accept traffic.

    This is where dependency checks belong, since a failing readiness probe
    only removes the pod from rotation until it recovers. The revocation
    mirror becomes such a check once it exists.
    """
    return {'status': 'ready'}
