# -*- coding: utf-8 -*-
#
# testing for the python client
#
# ------------------------------------------------


# imports
# -------
import httpx
import pytest

from catalog.client.models import ApiModel, ItemModel
from catalog.client.session import (
    Session,
    get_session,
    init_session,
    reset_session,
)


# fixtures
# --------
@pytest.fixture(autouse=True)
def clean():
    """
    Clear the default session around every test in this file.

    A global surviving between tests is how a suite starts passing in one
    order and failing in another, which is the whole reason the default is
    an instance we can discard rather than a client we cannot.
    """
    reset_session()
    yield
    reset_session()


@pytest.fixture
def items(session):
    """
    A handle on the items collection, bound to the in-process session.
    """
    return ItemModel(session=session)


# session
# -------
def test_session_reports_the_service_ready(session):
    assert session.ready() is True


def test_session_reads_health(session):
    data = session.health()

    assert data['status'] == 'up'
    assert data['env'] == 'test'


def test_session_is_not_ready_when_nothing_answers(config):
    # a service that cannot be reached is not ready -- that is a false
    # answer, not an exceptional one, and callers branch on it
    with Session(port=1, timeout=0.1) as session:
        assert session.ready() is False


def test_session_exposes_the_client(session):
    # the models send through this directly -- session adds no verbs of its
    # own, so anything httpx.Client can do is available to them
    assert isinstance(session.client, httpx.Client)


def test_session_defaults_to_the_configured_address(config):
    session = Session()

    assert session.host == config.CATALOG_HOST
    assert session.port == config.CATALOG_PORT
    session.close()


def test_session_leaves_a_borrowed_client_open(client):
    # closing something we did not open would take the fixture down with it
    with Session(client=client) as session:
        assert session.owned is False

    assert client.get('/health').status_code == 200


# construction
# ------------
def test_a_model_requires_a_key():
    # a model without a key looks finished and fails at its first call, so
    # it is refused at the point it is built instead
    with pytest.raises(ValueError):
        ApiModel(None)


def test_a_model_refuses_an_empty_key():
    with pytest.raises(ValueError):
        ApiModel('')


def test_a_subclass_supplies_its_own_key():
    assert ItemModel().key == 'items'


def test_a_model_can_be_built_without_a_subclass(session):
    # the base class is usable directly for a resource not worth naming
    names = [item['name'] for item in ApiModel('items', session=session).all()]
    assert 'sprocket' in names


# read
# ----
def test_model_lists_every_item(items):
    names = [item['name'] for item in items.all()]
    assert 'sprocket' in names


def test_model_gets_one_item(items):
    item = items.get('flange')

    assert item['name'] == 'flange'
    assert item['id'] == 2
    assert 'hardware' in item['tags']


def test_model_raises_for_a_missing_item(items):
    with pytest.raises(httpx.HTTPStatusError) as error:
        items.get('nothing')

    assert error.value.response.status_code == 404


def test_model_refuses_to_get_without_a_name(items):
    # without the guard this addresses the collection instead, and hands
    # back every item to a caller expecting one
    with pytest.raises(ValueError):
        items.get('')


def test_model_refuses_to_get_a_null_name(items):
    with pytest.raises(ValueError):
        items.get(None)


# write
# -----
def test_model_creates_an_item(items, seeded):
    item = items.create(name='gasket', desc='Seal', tags=['rubber'])

    assert item['name'] == 'gasket'
    assert item['id'] == 4
    assert item['created_at'] is not None

    # and the round trip shows it back
    assert 'gasket' in [entry['name'] for entry in items.all()]


def test_model_raises_for_a_duplicate_item(items, seeded):
    items.create(name='gasket')

    with pytest.raises(httpx.HTTPStatusError) as error:
        items.create(name='gasket')

    assert error.value.response.status_code == 409


# default session
# ---------------
def test_no_default_session_exists_until_one_is_built():
    assert get_session() is None


def test_init_session_installs_the_default(client):
    built = init_session(client=client)

    assert get_session() is built


def test_init_session_replaces_an_existing_default(client):
    first = init_session(client=client)
    second = init_session(client=client)

    assert get_session() is second
    assert first is not second


def test_reset_session_discards_the_default(client):
    init_session(client=client)
    reset_session()

    assert get_session() is None


def test_a_model_uses_the_session_it_was_given(session):
    init_session(port=1)

    # the bound session wins over the shared one, which points nowhere
    assert ItemModel(session=session).session is session


def test_a_model_falls_back_to_the_default_session(client):
    init_session(client=client)

    # nothing bound: the model finds the shared session itself
    assert 'sprocket' in [item['name'] for item in ItemModel().all()]


def test_a_bound_session_does_not_build_a_default(session):
    ItemModel(session=session).all()

    # binding a session must leave process state alone entirely
    assert get_session() is None


def test_a_model_builds_a_session_when_none_exists(client, monkeypatch):
    from catalog.client import models

    # nothing bound and nothing shared, so reading the property has to build
    # the default before the call can run at all
    monkeypatch.setattr(models, 'init_session', lambda: Session(client=client))

    assert ItemModel().all()
