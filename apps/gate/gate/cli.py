# -*- coding: utf-8 -*-
"""

    CLI interface for gate service

    Heavy imports live inside the command bodies rather than at module scope,
    so that printing help stays fast.

"""


# imports
# -------
import os

import click

from gate.config import config
from gate.logging import chalk


# main
# ----
@click.group('gate')
def main():
    """
    Authentication service for orbit.
    """


# commands
# --------
@main.command()
@click.option('-P', '--port', default=None, type=int, help='Port to serve on.')
def serve(port):
    """
    Serve the api with uvicorn.
    """
    import uvicorn

    # overrides
    if port:
        config.GATE_PORT = port

    # bind every interface so the service is reachable from outside its
    # container -- the bind address is deliberately not configurable, while
    # GATE_HOST describes where to reach the service from elsewhere.
    uvicorn.run(
        'gate.main:app',
        host='0.0.0.0',
        port=config.GATE_PORT,
        reload=config.ENV == 'dev',
        app_dir=os.path.realpath(os.path.join(os.path.dirname(__file__), '..')),
    )


@main.command()
@click.option(
    '-u', '--url',
    default=f'http://{config.GATE_HOST}:{config.GATE_PORT}',
    show_default=True,
    help='Base url to check, including scheme.',
)
def status(url):
    """
    Report which build of the service is answering.

    Exits non-zero when the service cannot be reached, so that scripts and
    pipelines can depend on it. Reports build metadata rather than uptime --
    gate has no health endpoint yet, and will report both once it does.
    """
    import httpx

    # a failed connection and a bad answer are different problems, so report
    # which one happened rather than collapsing both into 'unreachable'
    try:
        response = httpx.get(f'{url}/info', timeout=3)
        response.raise_for_status()
        data = response.json()
    except Exception as error:
        click.echo(chalk.cyan('status:  ') + chalk.red('unreachable'))
        click.echo(chalk.cyan('url:     ') + url)
        click.echo(chalk.cyan('error:   ') + type(error).__name__)
        raise SystemExit(1)

    # report what the service said about itself
    click.echo(chalk.cyan('status:  ') + chalk.green('up'))
    click.echo(chalk.cyan('url:     ') + url)
    click.echo(chalk.cyan('project: ') + data.get('project', '-'))
    click.echo(chalk.cyan('env:     ') + data.get('env', '-'))
    click.echo(chalk.cyan('version: ') + data.get('version', '-'))
    click.echo(chalk.cyan('commit:  ') + data.get('commit', '-'))


# tokens
# ------
@main.group()
def token():
    """
    Mint and inspect gate's own tokens.
    """


@token.command('mint')
@click.option('-s', '--sub', required=True, help='Subject: who the token is for.')
@click.option('-n', '--name', default=None, help='Display name. Defaults to the subject.')
@click.option('-e', '--email', default=None, help='Email address.')
@click.option('-g', '--group', 'groups', multiple=True, help='Group. Repeatable.')
@click.option('-t', '--ttl', default=None, type=int, help='Lifetime in hours.')
def mint_token(sub, name, email, groups, ttl):
    """
    Issue a signed token and print it.

    Prints the token alone, with nothing around it, so that it composes:
    curl -H "Authorization: Bearer $(gate token mint -s ada)"
    """
    from gate.auth.utils import mint

    click.echo(mint(sub, name=name, email=email, groups=list(groups), ttl_hours=ttl))


@token.command('decode')
@click.argument('token')
def decode_token(token):
    """
    Read a token and print what it says.

    Falls back to an unverified read when a token is merely expired, since
    the useful answer there is what it said and when it lapsed -- refusing
    to print anything explains nothing.
    """
    from datetime import datetime, timezone

    from fastapi import HTTPException

    import jwt

    from gate.auth.utils import decode

    trusted = True
    try:
        claims = decode(token)
    except HTTPException as error:
        detail = error.detail

        # an invalid signature makes every claim meaningless, so there is
        # nothing worth printing. an expired one is merely out of date.
        if detail != 'token expired':
            click.echo(chalk.cyan('status:  ') + chalk.red(detail))
            raise SystemExit(1)

        trusted = False

        # the signature has already been checked and passed; only the clock
        # refused this token, so its claims are worth printing under a
        # warning. read without verifying because an expired token cannot be
        # read any other way.
        claims = jwt.decode(token, options={'verify_signature': False})

    state = chalk.green('valid') if trusted else chalk.yellow('expired')
    click.echo(chalk.cyan('status:  ') + state)

    if not trusted:
        click.echo(chalk.cyan('warning: ') + chalk.yellow('claims below are unverified'))

    click.echo(chalk.cyan('sub:     ') + str(claims.get('sub', '-')))
    click.echo(chalk.cyan('name:    ') + str(claims.get('name') or '-'))
    click.echo(chalk.cyan('email:   ') + str(claims.get('email') or '-'))
    click.echo(chalk.cyan('groups:  ') + (', '.join(claims.get('groups') or []) or '-'))

    for field in ('iat', 'exp'):
        stamp = claims.get(field)
        when = datetime.fromtimestamp(stamp, timezone.utc).isoformat() if stamp else '-'
        click.echo(chalk.cyan(f'{field}:     ') + when)


# exec
# ----
if __name__ == '__main__':
    main()
