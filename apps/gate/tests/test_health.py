# -*- coding: utf-8 -*-
#
# testing for the health router
#
# recovered from ORB-002 with §4's compose healthcheck as its caller. ORB-002's
# test_ping and test_info are deliberately not brought with it -- test_main.py
# has covered both since the scaffold, and a second copy would drift.
#
# ------------------------------------------------


# probes
# ------
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
