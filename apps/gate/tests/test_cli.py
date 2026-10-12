# -*- coding: utf-8 -*-
#
# testing for cli commands
#
# ------------------------------------------------


# imports
# -------
from unittest.mock import MagicMock, patch

import jwt
import pytest
from click.testing import CliRunner

from gate.auth.utils import decode, mint
from gate.cli import main


# fixtures
# --------
@pytest.fixture
def runner():
    return CliRunner()


# help
# ----
def test_help(runner):
    result = runner.invoke(main, ['--help'])

    assert result.exit_code == 0
    assert 'serve' in result.output
    assert 'status' in result.output
    assert 'token' in result.output


# status
# ------
def test_status_reachable(runner):
    answer = MagicMock()
    answer.json.return_value = {
        'project': 'gate',
        'env': 'test',
        'version': '1.2.3',
        'commit': 'abc123',
    }

    with patch('httpx.get', return_value=answer):
        result = runner.invoke(main, ['status'])

    assert result.exit_code == 0
    assert 'up' in result.output
    assert '1.2.3' in result.output


def test_status_unreachable(runner):
    with patch('httpx.get', side_effect=Exception('connection refused')):
        result = runner.invoke(main, ['status'])

    assert result.exit_code == 1
    assert 'unreachable' in result.output


def test_status_url_override(runner):
    answer = MagicMock()
    answer.json.return_value = {'project': 'gate', 'env': 'test'}

    with patch('httpx.get', return_value=answer) as call:
        result = runner.invoke(main, ['status', '--url', 'http://example.test:9000'])

    assert result.exit_code == 0
    call.assert_called_once_with('http://example.test:9000/info', timeout=3)


# mint
# ----
def test_mint_prints_a_usable_token(runner, config):
    result = runner.invoke(main, ['token', 'mint', '--sub', 'ada'])

    assert result.exit_code == 0

    # nothing but the token, so it composes into a shell command
    assert decode(result.output.strip())['sub'] == 'ada'


def test_mint_carries_the_options(runner, config):
    result = runner.invoke(main, [
        'token', 'mint',
        '--sub', 'ada',
        '--name', 'Ada Lovelace',
        '--email', 'ada@orbit.test',
        '--group', 'catalog:read',
        '--group', 'catalog:write',
    ])
    claims = decode(result.output.strip())

    assert claims['name'] == 'Ada Lovelace'
    assert claims['email'] == 'ada@orbit.test'
    assert claims['groups'] == ['catalog:read', 'catalog:write']


def test_mint_requires_a_subject(runner):
    result = runner.invoke(main, ['token', 'mint'])

    assert result.exit_code != 0
    assert 'sub' in result.output


def test_mint_honours_a_ttl(runner, config):
    result = runner.invoke(main, ['token', 'mint', '--sub', 'ada', '--ttl', '1'])
    claims = decode(result.output.strip())

    assert round((claims['exp'] - claims['iat']) / 3600) == 1


# decode
# ------
def test_decode_reports_a_valid_token(runner, config):
    token = mint('ada', email='ada@orbit.test', groups=['catalog:read'])
    result = runner.invoke(main, ['token', 'decode', token])

    assert result.exit_code == 0
    assert 'valid' in result.output
    assert 'ada@orbit.test' in result.output
    assert 'catalog:read' in result.output


def test_decode_explains_an_expired_token(runner, config):
    # refusing to print anything explains nothing -- the useful answer is
    # what it said and when it lapsed
    token = mint('ada', email='ada@orbit.test', ttl_hours=-1)
    result = runner.invoke(main, ['token', 'decode', token])

    assert result.exit_code == 0
    assert 'expired' in result.output
    assert 'unverified' in result.output
    assert 'ada@orbit.test' in result.output


def test_decode_refuses_a_forged_token(runner, config):
    # an invalid signature makes every claim meaningless, so nothing is
    # printed from it at all
    forged = jwt.encode({'sub': 'root'}, 'not-our-key-but-long-enough', algorithm='HS256')
    result = runner.invoke(main, ['token', 'decode', forged])

    assert result.exit_code == 1
    assert 'invalid token' in result.output
    assert 'root' not in result.output


def test_decode_refuses_gibberish(runner, config):
    result = runner.invoke(main, ['token', 'decode', 'not-a-token'])

    assert result.exit_code == 1
    assert 'invalid token' in result.output
