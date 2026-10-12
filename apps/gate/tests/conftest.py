# -*- coding: utf-8 -*-
#
# pytest fixtures for gate
#
# ------------------------------------------------


# imports
# -------
import pytest


# constants
# ---------
# the fields a local .env can move under the suite. gate reads apps/gate/.env
# at import, so on a machine with a tenant configured the tests were handed
# different settings from the ones their own expectations are written against
# -- three callback tests were green only where no tenant existed, ci
# included. resetting the whole block closes that for every field rather than
# for the three that happened to fail.
AMBIENT = (
    'AUTH_PROVIDER_URL',
    'AUTH_AUTHORIZE_PATH',
    'AUTH_TOKEN_PATH',
    'AUTH_CLIENT_ID',
    'AUTH_CLIENT_SECRET',
    'AUTH_SCOPES',
    'GROUP_PREFIX',
    'GROUPS_CLAIM',
)


# fixtures
# --------
@pytest.fixture(scope='session')
def config():
    """
    Configuration for the test session.

    Pins every field a local .env can move, so the suite tests gate rather
    than the machine it happens to run on.

    Each one is reset to the default declared in `gate/config.py` rather than
    to a literal repeated here: those are the values a fresh clone runs with,
    and a default that changes there should still be visible from here. An
    ambient environment must not reach the suite; a deliberate change to what
    a fresh clone gets should turn a stale test red.
    """
    from gate.config import config

    config.ENV = 'test'

    for field in AMBIENT:
        setattr(config, field, type(config).model_fields[field].default)

    yield config


@pytest.fixture(scope='session')
def client(config):
    """
    Test client for the application.

    Entered as a context manager so that the lifespan handler runs -- without
    it, startup work never happens and application state is missing.
    """
    from fastapi.testclient import TestClient

    from gate.main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture(autouse=True)
def jar(client):
    """
    Empty the client's cookie jar before each test.

    The client is session-scoped and httpx keeps cookies, so a callback test
    that sets one leaves every later test holding a credential -- and the
    tests that would notice are the ones asserting a refusal, which would
    quietly start passing for the wrong reason. Cleared before rather than
    after, so what a test starts with does not depend on what ran before it.
    """
    client.cookies.clear()

    yield


@pytest.fixture
def user():
    """
    Claims of the caller the token fixture authenticates as.
    """
    return dict(
        sub='ada',
        name='Ada Lovelace',
        email='ada@orbit.test',
        groups=['catalog:read', 'catalog:write'],
    )


@pytest.fixture
def sign(config):
    """
    Encode claims into a token gate will accept.

    Tests build their own tokens rather than calling a minting helper --
    gate has none yet, and signing here keeps the test honest about what a
    credential actually is: claims plus a signature over the same key.
    """
    import jwt

    def encode(claims, **overrides):
        return jwt.encode(
            {**claims, **overrides},
            config.JWT_SECRET.get_secret_value(),
            algorithm=config.JWT_ALGORITHM,
        )

    return encode


@pytest.fixture
def token(sign, user):
    """
    A valid bearer token for the user fixture.
    """
    return sign(user)


@pytest.fixture
def bearer(token):
    """
    Authorization header carrying the token fixture.
    """
    return {'Authorization': f'Bearer {token}'}
