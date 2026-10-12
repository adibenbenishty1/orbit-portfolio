# -*- coding: utf-8 -*-
#
# testing for the endpoint nginx consults
#
# ------------------------------------------------


# imports
# -------
from datetime import datetime, timedelta, timezone

import jwt

from gate.auth.utils import COOKIE, scrub


# admit
# -----
def test_check_admits_a_valid_token(client, bearer):
    response = client.get('/auth/check', headers=bearer)

    assert response.status_code == 200
    assert response.text == 'Authenticated'


def test_check_carries_the_caller_identity(client, bearer, user):
    response = client.get('/auth/check', headers=bearer)

    assert response.headers['X-User-ID'] == user['sub']
    assert response.headers['X-User-Name'] == user['name']
    assert response.headers['X-User-Email'] == user['email']
    assert response.headers['X-Groups'] == ','.join(user['groups'])


def test_check_accepts_the_scheme_case_insensitively(client, token):
    # rfc 7235 defines the scheme as case-insensitive, and clients do vary
    response = client.get('/auth/check', headers={'Authorization': f'bearer {token}'})
    assert response.status_code == 200


def test_check_renders_absent_claims_as_empty(client, sign):
    # a token carrying only a subject is still a valid credential
    token = sign({'sub': 'ada'})
    response = client.get('/auth/check', headers={'Authorization': f'Bearer {token}'})

    assert response.status_code == 200
    assert response.headers['X-User-Email'] == ''
    assert response.headers['X-Groups'] == ''


# refuse
# ------
def test_check_refuses_a_request_with_no_credential(client):
    response = client.get('/auth/check')

    assert response.status_code == 401
    assert response.json()['detail'] == 'not authenticated'


def test_check_challenges_a_refused_request(client):
    # a 401 without a challenge tells a client it failed but not what to try
    response = client.get('/auth/check')
    assert response.headers['WWW-Authenticate'] == 'Bearer'


def test_check_refuses_the_wrong_scheme(client, token):
    response = client.get('/auth/check', headers={'Authorization': f'Basic {token}'})

    assert response.status_code == 401
    assert response.json()['detail'] == 'expected Bearer authorization'


def test_check_refuses_a_bare_token(client, token):
    # no scheme at all is the same mistake as the wrong one
    response = client.get('/auth/check', headers={'Authorization': token})
    assert response.status_code == 401


def test_check_refuses_an_empty_token(client):
    response = client.get('/auth/check', headers={'Authorization': 'Bearer '})

    assert response.status_code == 401
    assert response.json()['detail'] == 'missing bearer token'


def test_check_refuses_a_forged_token(client, user):
    forged = jwt.encode(user, 'not-the-signing-key-but-long-enough', algorithm='HS256')
    response = client.get('/auth/check', headers={'Authorization': f'Bearer {forged}'})

    assert response.status_code == 401
    assert response.json()['detail'] == 'invalid token'


def test_check_refuses_an_unsigned_token(client, user):
    # the algorithm is pinned at decode, so a token claiming alg:none is not
    # trusted to nominate its own verification
    unsigned = jwt.encode(user, key=None, algorithm='none')
    response = client.get('/auth/check', headers={'Authorization': f'Bearer {unsigned}'})

    assert response.status_code == 401


def test_check_refuses_an_expired_token(client, sign, user):
    expired = datetime.now(timezone.utc) - timedelta(hours=1)
    token = sign(user, exp=expired)
    response = client.get('/auth/check', headers={'Authorization': f'Bearer {token}'})

    # reported apart from an invalid token: the caller's remedy differs
    assert response.status_code == 401
    assert response.json()['detail'] == 'token expired'


def test_check_refuses_gibberish(client):
    response = client.get('/auth/check', headers={'Authorization': 'Bearer not.a.token'})
    assert response.status_code == 401


def test_check_emits_no_identity_when_refusing(client):
    # a refused request must not leave identity headers for nginx to copy
    response = client.get('/auth/check')

    assert 'X-User-ID' not in response.headers
    assert 'X-Groups' not in response.headers


# cookie
# ------
def test_check_admits_a_valid_cookie(client, token, user):
    # the browser arrives with no Authorization header at all
    client.cookies.set(COOKIE, token)
    response = client.get('/auth/check')

    assert response.status_code == 200
    assert response.headers['X-User-ID'] == user['sub']
    assert response.headers['X-Groups'] == ','.join(user['groups'])


def test_a_bearer_token_wins_over_a_cookie(client, sign, user, bearer):
    # the two are alternatives, not a chain. where both arrive, the header is
    # the one a caller deliberately set; the cookie the browser sent itself.
    client.cookies.set(COOKIE, sign(user, sub='someone-else'))
    response = client.get('/auth/check', headers=bearer)

    assert response.status_code == 200
    assert response.headers['X-User-ID'] == user['sub']


def test_check_refuses_a_forged_cookie(client, user):
    # a cookie is not trusted for being a cookie -- it ends at the same
    # decode as a bearer token, which is the point of putting one in it
    client.cookies.set(COOKIE, jwt.encode(user, 'not-the-signing-key-but-long-enough', algorithm='HS256'))
    response = client.get('/auth/check')

    assert response.status_code == 401
    assert response.json()['detail'] == 'invalid token'


def test_check_refuses_an_expired_cookie(client, sign, user):
    expired = datetime.now(timezone.utc) - timedelta(hours=1)
    client.cookies.set(COOKIE, sign(user, exp=expired))
    response = client.get('/auth/check')

    assert response.status_code == 401
    assert response.json()['detail'] == 'token expired'


def test_check_refuses_a_gibberish_cookie(client):
    # whatever is in a cookie is a caller's to choose, so it has to answer
    # 401 rather than 500
    client.cookies.set(COOKIE, 'not.a.token')
    response = client.get('/auth/check')

    assert response.status_code == 401


def test_an_empty_cookie_is_a_caller_with_no_credential(client):
    client.cookies.set(COOKIE, '')
    response = client.get('/auth/check')

    assert response.status_code == 401
    assert response.json()['detail'] == 'not authenticated'


# header safety
# -------------
def test_scrub_strips_newlines():
    # a newline inside a header value is how one header becomes two, in the
    # response every service downstream is about to trust
    assert scrub('Ada\r\nX-Groups: global:admin') == 'AdaX-Groups: global:admin'


def test_scrub_renders_an_absent_claim_as_empty():
    assert scrub(None) == ''


def test_check_survives_a_hostile_name(client, sign):
    hostile = sign({
        'sub': 'ada',
        'name': 'Ada\r\nX-Groups: global:admin',
        'groups': ['catalog:read'],
    })
    response = client.get('/auth/check', headers={'Authorization': f'Bearer {hostile}'})

    assert response.status_code == 200
    assert response.headers['X-Groups'] == 'catalog:read'
