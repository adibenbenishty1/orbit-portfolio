# -*- coding: utf-8 -*-
#
# testing for cli commands
#
# ------------------------------------------------


# imports
# -------
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from catalog.cli import main


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


# status
# ------
def test_status_healthy(runner):
    answer = MagicMock()
    answer.json.return_value = {
        'status': 'up',
        'env': 'test',
        'started': '2026-08-20T00:00:00Z',
        'uptime': 143,
    }

    with patch('httpx.get', return_value=answer):
        result = runner.invoke(main, ['status'])

    assert result.exit_code == 0
    assert 'up' in result.output
    assert '0:02:23' in result.output


def test_status_unreachable(runner):
    with patch('httpx.get', side_effect=Exception('connection refused')):
        result = runner.invoke(main, ['status'])

    assert result.exit_code == 1
    assert 'unreachable' in result.output


def test_status_unhealthy(runner):
    answer = MagicMock()
    answer.json.return_value = {'status': 'down', 'env': 'test', 'started': None, 'uptime': 0}

    with patch('httpx.get', return_value=answer):
        result = runner.invoke(main, ['status'])

    assert result.exit_code == 1
    assert 'down' in result.output


def test_status_url_override(runner):
    answer = MagicMock()
    answer.json.return_value = {'status': 'up', 'env': 'test', 'started': None, 'uptime': 0}

    with patch('httpx.get', return_value=answer) as call:
        result = runner.invoke(main, ['status', '--url', 'http://example.test:9000'])

    assert result.exit_code == 0
    call.assert_called_once_with('http://example.test:9000/health', timeout=3)
