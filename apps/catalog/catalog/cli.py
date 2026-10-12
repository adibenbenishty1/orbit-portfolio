# -*- coding: utf-8 -*-
"""

    CLI interface for catalog service

    Heavy imports live inside the command bodies rather than at module scope,
    so that printing help stays fast.

"""


# imports
# -------
import os
from datetime import timedelta

import click

from catalog.config import config
from catalog.logging import chalk


# main
# ----
@click.group('catalog')
def main():
    """
    Business service for orbit.
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
        config.CATALOG_PORT = port

    # bind every interface so the service is reachable from outside its
    # container -- the bind address is deliberately not configurable, while
    # CATALOG_HOST describes where to reach the service from elsewhere.
    uvicorn.run(
        'catalog.main:app',
        host='0.0.0.0',
        port=config.CATALOG_PORT,
        reload=config.ENV == 'dev',
        app_dir=os.path.realpath(os.path.join(os.path.dirname(__file__), '..')),
    )


@main.command()
@click.option(
    '-u', '--url',
    default=f'http://{config.CATALOG_HOST}:{config.CATALOG_PORT}',
    show_default=True,
    help='Base url to check, including scheme.',
)
def status(url):
    """
    Report service health and uptime.

    Exits non-zero when the service cannot be reached or reports itself
    unhealthy, so that scripts and pipelines can depend on it.
    """
    import httpx

    # a failed connection and a bad answer are different problems, so report
    # which one happened rather than collapsing both into 'unreachable'
    try:
        response = httpx.get(f'{url}/health', timeout=3)
        response.raise_for_status()
        data = response.json()
    except Exception as error:
        click.echo(chalk.cyan('status:  ') + chalk.red('unreachable'))
        click.echo(chalk.cyan('url:     ') + url)
        click.echo(chalk.cyan('error:   ') + type(error).__name__)
        raise SystemExit(1)

    # report what the service said about itself
    state = data.get('status', 'unknown')
    click.echo(chalk.cyan('status:  ') + (chalk.green(state) if state == 'up' else chalk.red(state)))
    click.echo(chalk.cyan('url:     ') + url)
    click.echo(chalk.cyan('env:     ') + data.get('env', '-'))
    click.echo(chalk.cyan('started: ') + (data.get('started') or '-'))
    click.echo(chalk.cyan('uptime:  ') + str(timedelta(seconds=int(data.get('uptime') or 0))))

    if state != 'up':
        raise SystemExit(1)

@click.group()
def db():
    """Database management commands."""
    pass


@db.command('init')
@click.option(
    '--name',
    'database_name',
    default=config.DB_NAME,
    show_default=True,
)
def db_init():
    """Initialize a PostgreSQL database."""
    from catalog.db.database import init_database

    init_database()
    click.echo(f'Database {config.DB_NAME} initialized.')


main.add_command(db)

# exec
# ----
if __name__ == '__main__':
    main()
