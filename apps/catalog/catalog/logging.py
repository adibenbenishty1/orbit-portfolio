#!/usr/bin/env python
"""

    Logging configuration

"""


# imports
# -------
import logging

from catalog.config import config


# formatters
# ----------
class chalk:
    """
    Terminal colour helpers, used by both log formatters and CLI output.
    """
    red     = lambda x: f'\033[91m{x}\033[0m'  ## noqa
    green   = lambda x: f'\033[92m{x}\033[0m'  ## noqa
    yellow  = lambda x: f'\033[93m{x}\033[0m'  ## noqa
    blue    = lambda x: f'\033[94m{x}\033[0m'  ## noqa
    magenta = lambda x: f'\033[95m{x}\033[0m'  ## noqa
    cyan    = lambda x: f'\033[96m{x}\033[0m'  ## noqa
    white   = lambda x: f'\033[97m{x}\033[0m'  ## noqa


# handlers
# --------
stamped = logging.StreamHandler()
stamped.setFormatter(logging.Formatter(
    fmt=' '.join([
        chalk.magenta('%(asctime)s'),
        chalk.blue('%(name)s'),
        chalk.green('%(levelname)s'),
        '%(message)s',
    ]),
    datefmt='%H:%M:%S',
))


# loggers
# -------
def logger(name):
    """
    Build a named logger writing to the stamped handler.

    Propagation is disabled so that records do not reach the root logger and
    appear twice once uvicorn installs its own handlers.

    Args:
        name (str) - Name the logger reports under.
    """
    log = logging.getLogger(name)
    log.propagate = False
    log.setLevel(config.LOG_LEVEL.upper())
    log.addHandler(stamped)
    return log


api = logger('api')
cli = logger('cli')
