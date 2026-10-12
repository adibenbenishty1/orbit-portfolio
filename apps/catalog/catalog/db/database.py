import re
from collections.abc import Generator

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

from catalog.config import config


def database_url(database_name: str | None = None) -> URL:
    """
    Build a PostgreSQL URL.

    By default, use Catalog's configured database.
    A different database may be supplied for administrative operations.
    """
    return URL.create(
        drivername='postgresql+psycopg',
        username=config.DB_USER,
        password=config.DB_PASSWORD,
        host=config.DB_HOST,
        port=config.DB_PORT,
        database=database_name or config.DB_NAME,
    )


engine: Engine = create_engine(database_url())

session_factory = sessionmaker(
    bind=engine,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """
    Provide a database session for a request.
    """
    database_session = session_factory()

    try:
        yield database_session
    finally:
        database_session.close()


def init_database() -> None:
    """
    Ensure that Catalog's configured PostgreSQL database exists.
    """
    if not re.fullmatch(r'[A-Za-z0-9_]+', config.DB_NAME):
        raise ValueError(f'Invalid database name: {config.DB_NAME}')

    admin_engine = create_engine(
        database_url('postgres'),
        isolation_level='AUTOCOMMIT',
    )

    try:
        with admin_engine.connect() as connection:
            exists = connection.scalar(
                text('SELECT 1 FROM pg_database WHERE datname = :name'),
                {'name': config.DB_NAME},
            )

            if not exists:
                connection.execute(
                    text(f'CREATE DATABASE "{config.DB_NAME}"')
                )
    finally:
        admin_engine.dispose()
