# -*- coding: utf-8 -*-
#
# testing for database lifecycle and isolation
#
# ------------------------------------------------

from contextlib import contextmanager

import pytest
from sqlalchemy import text




def test_database_selection(config, database, client):
    from catalog.db.database import get_db

    assert database.engine.url.database == config.DB_TEST_NAME
    with database.session_factory() as session:
        assert session.scalar(text('SELECT current_database()')) == config.DB_TEST_NAME
    with contextmanager(get_db)() as session:
        assert session.scalar(text('SELECT current_database()')) == config.DB_TEST_NAME


def test_canonical_ids(client):
    items = client.get('/items').json()
    assert [(item['id'], item['name']) for item in items] == [
        (1, 'sprocket'), (2, 'flange'), (3, 'grommet'),
    ]


def test_init_preserves_existing_database(config, database):
    from catalog.db.database import init_database
    with database.session_factory() as session:
        before = session.execute(text('SELECT * FROM items ORDER BY id')).all()
    init_database()
    with database.session_factory() as session:
        assert session.execute(text('SELECT * FROM items ORDER BY id')).all() == before


@pytest.mark.parametrize('name', ['', 'invalid-name', 'name"; DROP DATABASE orbit; --'])
def test_init_rejects_invalid_name(config, monkeypatch, name, database):
    from catalog.db.database import init_database
    with monkeypatch.context() as patch:
        patch.setattr(config, 'DB_NAME', name)
        with pytest.raises(ValueError, match='Invalid database name'):
            init_database()
