# -*- coding: utf-8 -*-
#
# testing for the redirect out to the identity provider
#
# ------------------------------------------------


# imports
# -------
from urllib.parse import parse_qs, urlparse

import pytest


# helpers
# -------
def redirect(client, **params):
    """
    Follow no redirects, and return the parsed Location of the response.
    """
    response = client.get('/auth/login', params=params, follow_redirects=False)

    assert response.status_code == 302, response.status_code

    location = urlparse(response.headers['location'])
    return location, parse_qs(location.query)


# provider
# --------
def test_login_redirects_to_the_configured_provider(client, config):
    location, _ = redirect(client)

    assert location.hostname == config.AUTH_PROVIDER_URL.host
    assert location.path == config.AUTH_AUTHORIZE_PATH


def test_login_sends_the_authorize_parameters(client, config):
    _, query = redirect(client)

    assert query['client_id'] == [config.AUTH_CLIENT_ID]
    assert query['response_type'] == ['code']
    assert query['scope'] == [config.AUTH_SCOPES]


def test_login_redirects_rather_than_answering(client):
    # 302, not fastapi's default 307 -- an authorize redirect is a plain get
    response = client.get('/auth/login', follow_redirects=False)
    assert response.status_code == 302


# callback
# --------
def test_login_derives_the_callback_from_the_request(client):
    # not configured: the callback follows gate wherever it is deployed
    _, query = redirect(client)

    assert query['redirect_uri'] == ['http://testserver/auth/callback']


def test_login_trusts_the_forwarded_scheme(client):
    # behind nginx the request arrives over http even when the browser used
    # https. build the callback from that and the provider refuses it.
    response = client.get(
        '/auth/login',
        headers={'X-Forwarded-Proto': 'https'},
        follow_redirects=False,
    )
    query = parse_qs(urlparse(response.headers['location']).query)

    assert query['redirect_uri'] == ['https://testserver/auth/callback']


# destination
# -----------
def test_login_carries_the_destination_in_state(client):
    _, query = redirect(client, rd='/items')

    assert query['state'] == ['/items']


def test_login_states_none_without_a_destination(client):
    _, query = redirect(client)

    assert query['state'] == ['none']


@pytest.mark.parametrize('rd', [
    'https://evil.test/steal',
    'http://evil.test/steal',
    '//evil.test/steal',          # protocol-relative: absolute to a browser
    'items',                      # no leading slash
])
def test_login_refuses_an_absolute_destination(client, rd):
    # this value survives the round trip and is eventually redirected to, so
    # an absolute url here makes gate an open redirect
    response = client.get('/auth/login', params={'rd': rd}, follow_redirects=False)

    assert response.status_code == 400
    assert response.json()['detail'] == 'rd must be a relative path'


# access
# ------
def test_login_needs_no_credential(client):
    # the endpoint that exists to get you one cannot require one
    response = client.get('/auth/login', follow_redirects=False)

    assert response.status_code == 302
