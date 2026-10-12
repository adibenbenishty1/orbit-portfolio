# -*- coding: utf-8 -*-
#
# testing for the application scaffold
#
# ------------------------------------------------


# routes
# ------
def test_ping(client):
    response = client.get('/ping')

    assert response.status_code == 200
    assert response.json()['status'] == 'ok'


def test_info(client):
    response = client.get('/info')
    data = response.json()

    assert response.status_code == 200
    assert data['project'] == 'gate'
    assert data['env'] == 'test'
    assert 'version' in data
    assert 'commit' in data


# lifespan
# --------
def test_startup_records_when_it_started(client):
    # the lifespan handler only runs when the client is entered as a context
    # manager, so this fails loudly if that ever stops happening
    from gate.main import app

    assert app.state.started is not None


# surface
# -------
def test_the_served_surface(client):
    # pinned deliberately: a route appearing here that nobody meant to add is
    # a security service growing an entrance nobody reviewed.
    #
    # read from the openapi document rather than app.routes -- an included
    # router appears there as one opaque object with no paths on it, so
    # walking the route list silently under-reports the real surface.
    served = set(client.get('/openapi.json').json()['paths'])

    assert served == {
        '/ping', '/info', '/metrics',
        '/health', '/health/alive', '/health/ready',
        '/auth/check', '/auth/login', '/auth/callback',
    }


def test_prometheus_is_exposed(client):
    response = client.get('/metrics')

    assert response.status_code == 200
    assert 'orbit_gate' in response.text
