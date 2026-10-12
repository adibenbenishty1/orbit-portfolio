# -*- coding: utf-8 -*-
#
# testing for the callback leg and the code exchange
#
# ------------------------------------------------


# imports
# -------
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import jwt
import pytest

from gate.auth.utils import COOKIE


# fixtures
# --------
# claims shaped the way the provider sends them: an opaque subject, and groups
# still in the directory's spelling rather than gate's.
CLAIMS = dict(
    sub='auth0|abc123',
    name='Ada Lovelace',
    email='ada@orbit.test',
    groups=['orbit-catalog-read'],
    iss='https://tenant.example/',
    aud='orbit-dev-client',
)


def id_token(claims=None):
    """
    An id_token shaped like the provider's.

    Signed with a key gate does not have, which is the whole point: nothing
    on this path verifies the signature, so a token gate could never have
    produced still has to be readable.
    """
    return jwt.encode(claims or CLAIMS, 'the-providers-own-key-not-gates-own', algorithm='HS256')


@contextmanager
def provider(status_code=200, payload=None, text=''):
    """
    Stand in for the provider's token endpoint.

    Yields the patched client so a test can assert on what gate sent, which is
    where the interesting failures live -- a wrong redirect_uri is refused by
    the real provider before it shows the caller anything.
    """
    response = MagicMock(status_code=status_code, text=text)
    response.json.return_value = payload if payload is not None else {}

    client = AsyncMock()
    client.post.return_value = response

    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=client)
    manager.__aexit__ = AsyncMock(return_value=False)

    with patch('httpx.AsyncClient', return_value=manager):
        yield client


def sent(client):
    """
    The keyword arguments gate posted to the token endpoint.
    """
    return client.post.call_args.kwargs


def carried(response, config):
    """
    Read the claims out of the token the callback set as a cookie.

    Verified with gate's own secret, like `minted` -- the cookie holds the
    same credential the json ending hands over, which is the property that
    keeps the browser and the api client on one code path.
    """
    return jwt.decode(
        response.cookies[COOKIE],
        config.JWT_SECRET.get_secret_value(),
        algorithms=[config.JWT_ALGORITHM],
    )


def cookie(response):
    """
    The raw Set-Cookie header, where the attributes live.
    """
    return response.headers['set-cookie']


def minted(response, config):
    """
    Read the claims out of the token the callback answered with.

    Decoded with gate's own secret and verified, unlike the provider's token
    -- if this succeeds at all then what came back is gate's, since the
    provider's key is one gate does not have.
    """
    return jwt.decode(
        response.json()['token'],
        config.JWT_SECRET.get_secret_value(),
        algorithms=[config.JWT_ALGORITHM],
    )


# the token gate answers with
# ---------------------------
def test_callback_returns_a_token_gate_signed_itself(client, config):
    # no destination, so this is the json ending. the cookie ending carries
    # the same token and is asserted on its own further down.
    with provider(payload={'id_token': id_token()}):
        response = client.get('/auth/callback?code=abc')

    assert response.status_code == 200
    assert minted(response, config)['sub'] == 'auth0|abc123'
    assert minted(response, config)['email'] == 'ada@orbit.test'


def test_callback_reads_a_token_it_could_not_have_signed(client, config):
    # the provider signs with its own key, and gate still read the claims out
    # of it. this passing is the unverified decode working as intended.
    with provider(payload={'id_token': id_token()}):
        response = client.get('/auth/callback?code=abc')

    assert minted(response, config)['name'] == 'Ada Lovelace'


def test_the_providers_token_does_not_survive_the_callback(client, config):
    # gate's claim set is deliberately small. the provider's own claims
    # describe the provider, and nothing downstream should be shaped by them.
    with provider(payload={'id_token': id_token()}):
        response = client.get('/auth/callback?code=abc')

    claims = minted(response, config)
    assert 'iss' not in claims
    assert 'aud' not in claims


# groups
# ------
def test_callback_normalises_the_provider_groups(client, config):
    # the callback is the boundary: auth0's spelling goes in, gate's
    # vocabulary comes out, and no other caller converts.
    with provider(payload={'id_token': id_token()}):
        response = client.get('/auth/callback?code=abc')

    assert minted(response, config)['groups'] == ['catalog:read']


def test_callback_drops_groups_that_are_not_ours(client, config):
    claims = dict(CLAIMS, groups=['orbit-catalog-read', 'everyone', 'sales-crm-admin'])

    with provider(payload={'id_token': id_token(claims)}):
        response = client.get('/auth/callback?code=abc')

    assert minted(response, config)['groups'] == ['catalog:read']


def test_the_groups_claim_name_is_configurable(client, config, monkeypatch):
    # auth0 requires a custom claim to be namespaced and drops a plain one, so
    # the real claim name is a uri rather than `groups`
    namespaced = 'https://orbit.test/groups'
    monkeypatch.setattr(config, 'GROUPS_CLAIM', namespaced)

    claims = {k: v for k, v in CLAIMS.items() if k != 'groups'}
    claims[namespaced] = ['orbit-catalog-write']

    with provider(payload={'id_token': id_token(claims)}):
        response = client.get('/auth/callback?code=abc')

    assert minted(response, config)['groups'] == ['catalog:write']


def test_a_token_with_no_groups_claim_mints_an_empty_list(client, config):
    # what auth0 sends until a post-login action injects the claim
    claims = {k: v for k, v in CLAIMS.items() if k != 'groups'}

    with provider(payload={'id_token': id_token(claims)}):
        response = client.get('/auth/callback?code=abc')

    assert minted(response, config)['groups'] == []


# the whole way through
# ---------------------
def test_a_token_from_the_callback_authorises_a_request(client, config):
    # login to authorised request in one test. everything before this proves a
    # leg; this proves the loop -- the credential the callback hands out is one
    # /check accepts, and the groups arrive downstream already normalised.
    with provider(payload={'id_token': id_token()}):
        response = client.get('/auth/callback?code=abc')

    granted = client.get(
        '/auth/check',
        headers={'Authorization': f'Bearer {response.json()["token"]}'},
    )

    assert granted.status_code == 200
    assert granted.headers['X-User-ID'] == 'auth0|abc123'
    assert granted.headers['X-Groups'] == 'catalog:read'


# exchange
# --------
def test_callback_exchanges_the_code_it_was_given(client):
    with provider(payload={'id_token': id_token()}) as call:
        client.get('/auth/callback?code=the-real-code')

    assert sent(call)['data']['code'] == 'the-real-code'
    assert sent(call)['data']['grant_type'] == 'authorization_code'


def test_callback_authenticates_as_gate(client, config):
    # credentials go in the Authorization header, not the form body
    with provider(payload={'id_token': id_token()}) as call:
        client.get('/auth/callback?code=abc')

    assert sent(call)['auth'] == (
        config.AUTH_CLIENT_ID,
        config.AUTH_CLIENT_SECRET.get_secret_value(),
    )
    assert 'client_secret' not in sent(call)['data']


# redirect uri
# ------------
def test_both_legs_send_the_same_redirect_uri(client):
    # the one that bites: a provider refuses a redirect_uri it does not
    # recognise before showing the caller anything, so login and the exchange
    # have to produce a byte-identical string.
    outbound = client.get('/auth/login', follow_redirects=False)
    login_uri = parse_qs(urlparse(outbound.headers['location']).query)['redirect_uri'][0]

    with provider(payload={'id_token': id_token()}) as call:
        client.get('/auth/callback?code=abc')

    assert sent(call)['data']['redirect_uri'] == login_uri
    assert login_uri == 'http://testserver/auth/callback'


def test_the_redirect_uri_respects_the_forwarded_scheme(client):
    # gate runs behind nginx, which terminates tls and forwards plain http
    with provider(payload={'id_token': id_token()}) as call:
        client.get('/auth/callback?code=abc', headers={'X-Forwarded-Proto': 'https'})

    assert sent(call)['data']['redirect_uri'] == 'https://testserver/auth/callback'


# refusals
# --------
@pytest.mark.parametrize('query', [
    '',
    '?state=/items',
    '?error=access_denied',
    '?error=access_denied&error_description=User+declined+consent',
])
def test_callback_refuses_anything_without_a_usable_code(client, query):
    response = client.get(f'/auth/callback{query}')

    assert response.status_code == 400
    assert response.json()['detail'] == 'authentication did not complete'


def test_callback_does_not_echo_the_provider_error(client):
    # anyone can request this url with any error on it. reflecting that text
    # back makes gate a mouthpiece for whatever was put in the query string.
    response = client.get('/auth/callback?error=<script>&error_description=leak-me')

    assert response.status_code == 400
    assert 'leak-me' not in response.text
    assert 'script' not in response.text


def test_callback_refuses_a_refused_exchange(client):
    with provider(status_code=403, text='Callback URL mismatch'):
        response = client.get('/auth/callback?code=stale')

    assert response.status_code == 400
    assert response.json()['detail'] == 'the identity provider refused the code exchange'


def test_a_refused_exchange_does_not_leak_the_provider_reason(client):
    # the provider explains our configuration, not the caller's mistake
    with provider(status_code=403, text='Callback URL mismatch'):
        response = client.get('/auth/callback?code=stale')

    assert 'mismatch' not in response.text


def test_callback_refuses_a_response_with_no_id_token(client):
    # a provider returns none when the openid scope was not asked for
    with provider(payload={'access_token': 'not-what-we-need'}):
        response = client.get('/auth/callback?code=abc')

    assert response.status_code == 400
    assert response.json()['detail'] == 'the identity provider returned no id_token'


def test_callback_refuses_an_id_token_with_no_subject(client):
    # oidc requires sub, so a token without one is a broken provider rather
    # than a caller's mistake -- but it is still refused rather than allowed
    # to reach mint() and surface as a 500
    claims = {k: v for k, v in CLAIMS.items() if k != 'sub'}

    with provider(payload={'id_token': id_token(claims)}):
        response = client.get('/auth/callback?code=abc')

    assert response.status_code == 400
    assert response.json()['detail'] == 'the identity provider returned no subject'


# the cookie ending
# -----------------
def test_a_callback_with_a_destination_redirects_there(client):
    # the loop the cookie exists to close: somebody asked for /items, was
    # sent away to authenticate, and lands back on /items holding something
    with provider(payload={'id_token': id_token()}):
        response = client.get('/auth/callback?code=abc&state=/items', follow_redirects=False)

    assert response.status_code == 302
    assert response.headers['location'] == '/items'


def test_the_redirect_carries_the_credential_in_a_cookie(client, config):
    with provider(payload={'id_token': id_token()}):
        response = client.get('/auth/callback?code=abc&state=/items', follow_redirects=False)

    assert carried(response, config)['sub'] == 'auth0|abc123'
    assert carried(response, config)['groups'] == ['catalog:read']


def test_the_cookie_is_not_readable_by_javascript(client):
    # a credential javascript can read is how one xss becomes a stolen token
    with provider(payload={'id_token': id_token()}):
        response = client.get('/auth/callback?code=abc&state=/items', follow_redirects=False)

    assert 'httponly' in cookie(response).lower()


def test_the_cookie_travels_on_every_path(client):
    # /auth/check is consulted for every route, so the cookie has to reach it
    with provider(payload={'id_token': id_token()}):
        response = client.get('/auth/callback?code=abc&state=/items', follow_redirects=False)

    assert 'Path=/' in cookie(response)


def test_the_cookie_is_sent_on_a_navigation_from_the_provider(client):
    # Strict would withhold it on a navigation arriving from the provider's
    # domain, which is the one navigation this whole flow consists of
    with provider(payload={'id_token': id_token()}):
        response = client.get('/auth/callback?code=abc&state=/items', follow_redirects=False)

    assert 'samesite=lax' in cookie(response).lower()


def test_the_cookie_sets_no_domain(client):
    # there is no parent domain for localhost, and setting one makes the
    # browser discard the cookie with nothing logged anywhere
    with provider(payload={'id_token': id_token()}):
        response = client.get('/auth/callback?code=abc&state=/items', follow_redirects=False)

    assert 'domain' not in cookie(response).lower()


def test_the_cookie_dies_with_the_token_it_carries(client, config):
    # a cookie outliving its token is a browser that looks logged in and 401s
    with provider(payload={'id_token': id_token()}):
        response = client.get('/auth/callback?code=abc&state=/items', follow_redirects=False)

    assert f'Max-Age={config.JWT_TTL_HOURS * 3600}' in cookie(response)


def test_the_cookie_is_not_secure_over_plain_http(client):
    # the landmine: a Secure cookie is dropped silently over http, which is
    # what http://localhost is -- login appears to work and every check 401s
    with provider(payload={'id_token': id_token()}):
        response = client.get('/auth/callback?code=abc&state=/items', follow_redirects=False)

    assert 'secure' not in cookie(response).lower()


def test_the_cookie_is_secure_behind_a_terminated_tls(client):
    with provider(payload={'id_token': id_token()}):
        response = client.get(
            '/auth/callback?code=abc&state=/items',
            headers={'X-Forwarded-Proto': 'https'},
            follow_redirects=False,
        )

    assert 'secure' in cookie(response).lower()


# the ending without a destination
# --------------------------------
def test_a_callback_with_no_destination_still_answers_json(client, config):
    with provider(payload={'id_token': id_token()}):
        response = client.get('/auth/callback?code=abc', follow_redirects=False)

    assert response.status_code == 200
    assert minted(response, config)['sub'] == 'auth0|abc123'
    assert 'set-cookie' not in response.headers


def test_the_no_destination_sentinel_is_read_as_absence(client):
    # login sends the word rather than an empty state, so it comes back as a
    # string that is not a path. recognised before validation, or the caller
    # is refused with a 400 for having asked for nothing in particular.
    with provider(payload={'id_token': id_token()}):
        response = client.get('/auth/callback?code=abc&state=none', follow_redirects=False)

    assert response.status_code == 200
    assert 'set-cookie' not in response.headers


def test_a_destination_that_came_back_absolute_is_refused(client):
    # state travelled through a browser and was not ours in between, so it is
    # validated on the way out rather than trusted for having round-tripped
    with provider(payload={'id_token': id_token()}):
        response = client.get('/auth/callback?code=abc&state=//evil.test', follow_redirects=False)

    assert response.status_code == 400
    assert response.json()['detail'] == 'rd must be a relative path'


# the whole way through, in a browser
# -----------------------------------
def test_the_cookie_from_the_callback_authorises_a_request(client):
    # the browser twin of the bearer test above. nothing sets a header here:
    # the callback set a cookie, the client sends it back the way a browser
    # would, and /check answers with the identity that was minted.
    with provider(payload={'id_token': id_token()}):
        client.get('/auth/callback?code=abc&state=/items', follow_redirects=False)

    granted = client.get('/auth/check')

    assert granted.status_code == 200
    assert granted.headers['X-User-ID'] == 'auth0|abc123'
    assert granted.headers['X-Groups'] == 'catalog:read'
