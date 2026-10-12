# -*- coding: utf-8 -*-
"""

    The connection to a running catalog.

    One object owning one http client, so that the models above it never
    build a url or read a status code. A module-level default instance
    exists so an interactive user can import a model and query it with no
    setup call -- but it holds a Session rather than a bare client, so a
    test or a second host can construct its own without disturbing it.

"""


# imports
# -------
import httpx

from catalog.config import config


# session
# -------
class Session:
    """
    A connection to a catalog service.

    Args:
        host (str) - Host to reach the service on. Defaults to config.
        port (int) - Port to reach the service on. Defaults to config.
        timeout (float) - Seconds to wait for a response.
        client (httpx.Client) - Ready-made client to send through, instead of
            one built from host and port. Tests pass a client wired straight
            into the application, with no socket in between.
    """

    def __init__(self, host=None, port=None, timeout=10, client=None):
        self.host = host or config.CATALOG_HOST
        self.port = port or config.CATALOG_PORT
        self.url = f'http://{self.host}:{self.port}'

        # a caller that supplied its own client keeps ownership of it.
        # closing something we did not open would, in the test suite, take
        # the fixture down with the session that borrowed it.
        self.owned = client is None
        self.client = client or httpx.Client(
            base_url=self.url, timeout=timeout, follow_redirects=True
        )

    def __repr__(self):
        return f'Session({self.client.base_url})'

    # service
    # -------
    def health(self):
        """
        The service's own account of itself: status, environment, uptime.
        """
        response = self.client.get('/health')
        response.raise_for_status()

        return response.json()

    def ready(self):
        """
        Whether the service is up and accepting traffic.

        Answers False rather than raising when the service cannot be reached
        at all. 'Is it ready' has a false answer in that case, not an
        exceptional one, and callers use this to decide whether to proceed.
        """
        try:
            response = self.client.get('/health/ready')
            response.raise_for_status()
        except httpx.HTTPError:
            return False

        return response.json().get('status') == 'ready'

    # lifecycle
    # ---------
    def close(self):
        """
        Release the connection pool, unless the client came from elsewhere.
        """
        if self.owned:
            self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *error):
        self.close()


# default
# -------
# the session models reach for when the caller has not supplied one. it is
# private because it is replaced through the two functions below, which keep
# closing the old one from being something every caller has to remember.
_default = None


def init_session(**kwargs):
    """
    Build the default session, replacing any session already there.

    Args:
        kwargs - Passed to Session.
    """
    global _default

    reset_session()
    _default = Session(**kwargs)

    return _default


def get_session():
    """
    The default session, or None if nothing has built one yet.
    """
    return _default


def reset_session():
    """
    Discard the default session, closing it if it owns its client.

    Mostly for tests: a global that survives between them is how a suite
    starts passing in one order and failing in another.
    """
    global _default

    if _default is not None:
        _default.close()

    _default = None
