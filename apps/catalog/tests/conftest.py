# -*- coding: utf-8 -*-
#
# pytest fixtures for catalog
#
# ------------------------------------------------


# imports
# -------
import pytest


# fixtures
# --------
@pytest.fixture(scope='session')
def config():
    """
    Configuration for the test session.
    """
    from catalog.config import config

    if config.ENV.lower() not in {'local', 'dev', 'development', 'test', 'testing'}:
        raise RuntimeError('Tests must not run against a production configuration')
    config.ENV = 'test'
    config.DB_NAME = config.DB_TEST_NAME

    yield config


@pytest.fixture(scope='session', autouse=True)
def database(config):
    """
    Initialize the database selected for the test session.
    """
    from alembic import command
    from catalog.db import database
    from alembic.config import Config

    try:
        database.init_database()

        alembic_config = Config('alembic.ini')
        command.upgrade(alembic_config, 'head')
        yield database
    finally:
        database.engine.dispose()

@pytest.fixture(scope='session')
def client(config, database):
    """
    Test client for the application.

    Entered as a context manager so that the lifespan handler runs -- without
    it, startup work never happens and application state is missing.
    """
    from fastapi.testclient import TestClient

    from catalog.main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture(autouse=True)
def seeded(database):
    """
    Reset the PostgreSQL item store around every test.
    """
    from datetime import datetime, timezone

    from sqlalchemy import text

    from catalog.db.models import Item

    catalog = [
        ('sprocket', 'Toothed wheel driving a chain', ['hardware', 'rotating']),
        ('flange', 'Rim for strength or attachment', ['hardware']),
        ('grommet', 'Protective ring lining a hole', ['hardware', 'rubber']),
    ]

    def reset():
        with database.session_factory() as session:
            session.execute(text('TRUNCATE TABLE items RESTART IDENTITY'))
            session.add_all([
                Item(
                    name=name,
                    desc=desc,
                    tags=tags,
                    created_at=datetime.now(timezone.utc),
                )
                for name, desc, tags in catalog
            ])
            session.commit()

    reset()
    yield
    reset()



@pytest.fixture
def session(client):
    """
    A client session that reaches the application in process.

    It borrows the test client rather than opening a socket, so there is no
    server to start and no port to pick -- and because the session did not
    open that client, closing the session leaves it alone for the next test.
    """
    from catalog.client.session import Session

    with Session(client=client) as session:
        yield session
