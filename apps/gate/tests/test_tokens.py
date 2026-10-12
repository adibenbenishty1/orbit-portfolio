# -*- coding: utf-8 -*-
#
# testing for minting and reading gate's own tokens
#
# ------------------------------------------------


# imports
# -------
import time

import jwt
import pytest
from fastapi import HTTPException

from gate.auth.utils import decode, mint


# mint
# ----
def test_mint_round_trips_through_decode(config):
    claims = decode(mint('ada'))

    assert claims['sub'] == 'ada'


def test_mint_carries_every_claim(config):
    claims = decode(mint(
        'ada',
        name='Ada Lovelace',
        email='ada@orbit.test',
        groups=['catalog:read', 'catalog:write'],
    ))

    assert claims['name'] == 'Ada Lovelace'
    assert claims['email'] == 'ada@orbit.test'
    assert claims['groups'] == ['catalog:read', 'catalog:write']


def test_mint_falls_back_to_the_subject_for_a_name(config):
    # a token always carries something printable, so a caller displaying the
    # name never has to handle None
    assert decode(mint('ada'))['name'] == 'ada'


def test_mint_defaults_email_and_groups(config):
    claims = decode(mint('ada'))

    assert claims['email'] is None
    assert claims['groups'] == []


def test_mint_refuses_a_token_with_no_subject(config):
    # a credential identifying nobody would still verify, and would name
    # nobody in every header built from it
    with pytest.raises(ValueError):
        mint('')


# lifetime
# --------
def test_mint_stamps_when_it_was_issued(config):
    claims = decode(mint('ada'))

    assert claims['iat'] <= int(time.time()) + 1


def test_mint_expires_after_the_configured_ttl(config):
    claims = decode(mint('ada'))
    hours = (claims['exp'] - claims['iat']) / 3600

    assert round(hours) == config.JWT_TTL_HOURS


def test_mint_honours_an_explicit_ttl(config):
    claims = decode(mint('ada', ttl_hours=1))
    hours = (claims['exp'] - claims['iat']) / 3600

    assert round(hours) == 1


def test_a_lapsed_token_is_refused(config):
    with pytest.raises(HTTPException) as error:
        decode(mint('ada', ttl_hours=-1))

    assert error.value.detail == 'token expired'


def test_decode_refuses_a_token_signed_by_anyone(config):
    # the counterpart to the callback reading the provider's token without
    # checking it: what arrives from a caller is verified, whatever its shape
    forged = jwt.encode({'sub': 'root'}, 'not-our-key-but-long-enough', algorithm='HS256')

    with pytest.raises(HTTPException) as error:
        decode(forged)

    assert error.value.detail == 'invalid token'


# admission
# ---------
def test_a_minted_token_is_admitted_by_check(client, config):
    token = mint('ada', email='ada@orbit.test', groups=['catalog:read'])
    response = client.get('/auth/check', headers={'Authorization': f'Bearer {token}'})

    assert response.status_code == 200
    assert response.headers['X-User-Email'] == 'ada@orbit.test'
    assert response.headers['X-Groups'] == 'catalog:read'
