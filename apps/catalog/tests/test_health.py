# -*- coding: utf-8 -*-
#
# testing for health and metadata endpoints
#
# ------------------------------------------------


# probes
# ------
def test_ping(client):
    response = client.get('/ping')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'


def test_alive(client):
    response = client.get('/health/alive')
    assert response.status_code == 200
    assert response.json()['status'] == 'alive'


def test_ready(client):
    response = client.get('/health/ready')
    assert response.status_code == 200
    assert response.json()['status'] == 'ready'


# health
# ------
def test_health(client):
    response = client.get('/health')
    data = response.json()

    assert response.status_code == 200
    assert data['status'] == 'up'
    assert data['env'] == 'test'
    assert data['started'] is not None
    assert data['uptime'] >= 0


# metadata
# --------
def test_info(client):
    response = client.get('/info')
    data = response.json()

    assert response.status_code == 200
    assert data['project'] == 'catalog'
    assert data['env'] == 'test'
    assert data['version'] == 'unknown'
    assert data['commit'] == 'unknown'
