# -*- coding: utf-8 -*-
#
# testing for items endpoints
#
# ------------------------------------------------


# read
# ----
def test_list_items(client):
    response = client.get('/items')
    assert response.status_code == 200

    names = [item['name'] for item in response.json()]
    assert 'sprocket' in names


def test_get_item(client):
    response = client.get('/items/flange')
    data = response.json()

    assert response.status_code == 200
    assert data['name'] == 'flange'
    assert data['id'] == 2
    assert 'hardware' in data['tags']


def test_get_item_missing(client):
    response = client.get('/items/nothing')
    assert response.status_code == 404
    assert 'nothing' in response.json()['detail']


# write
# -----
def test_create_item(client, seeded):
    response = client.post('/items', json={
        'name': 'gasket',
        'desc': 'Seal between two surfaces',
        'tags': ['rubber'],
    })
    data = response.json()

    assert response.status_code == 201
    assert data['name'] == 'gasket'
    assert data['id'] == 4
    assert data['created_at'] is not None

    # and it is now listed
    names = [item['name'] for item in client.get('/items').json()]
    assert 'gasket' in names


def test_create_item_duplicate(client, seeded):
    assert client.post('/items', json={'name': 'gasket'}).status_code == 201

    response = client.post('/items', json={'name': 'gasket'})
    assert response.status_code == 409
    assert 'already exists' in response.json()['detail']


def test_create_item_requires_name(client):
    response = client.post('/items', json={'desc': 'nameless'})
    assert response.status_code == 422
