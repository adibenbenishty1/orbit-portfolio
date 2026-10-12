# -*- coding: utf-8 -*-
"""

    Application configuration

"""


# imports
# -------
from pydantic_settings import BaseSettings, SettingsConfigDict


# config
# ------
class Config(BaseSettings):
    """
    Settings for the catalog service.

    Fields are flat and uppercase so that each one maps directly onto an
    environment variable, and from there onto a single key in a helm values
    file. Every field has a working default, so a fresh clone runs with no
    setup. Unknown keys are ignored, which lets one .env file serve several
    services.
    """
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    # basic
    ENV: str = 'local'
    PROJECT: str = 'catalog'

    # build
    VERSION: str = 'unknown'
    COMMIT: str = 'unknown'

    # server
    # CATALOG_HOST is where to reach the service from elsewhere -- used by the
    # cli, not as a bind address. The server always binds every interface.
    CATALOG_HOST: str = 'localhost'
    CATALOG_PORT: int = 5000

    # database
    DB_HOST: str = 'localhost'
    DB_PORT: int = 5432
    DB_NAME: str = 'orbit'
    DB_TEST_NAME: str = 'orbit_test'
    DB_USER: str = 'postgres'
    DB_PASSWORD: str = 'orbit-dev'

    # logging
    LOG_LEVEL: str = 'INFO'

    # monitor
    PROMETHEUS_ENABLED: bool = True
    PROMETHEUS_NAMESPACE: str = 'orbit'
    PROMETHEUS_SUBSYSTEM: str = 'catalog'


# instance
# --------
config = Config()
