# -*- coding: utf-8 -*-
"""

    Resources, as classes.

    Every resource in the api is the same few calls pointed at a different
    path, so the calls live once on a base class and a subclass supplies
    only what makes it different -- its key, which is the path segment its
    collection is served under. Adding a resource is a constructor, and
    none of it is an http call.

"""


# imports
# -------
from catalog.client.session import get_session, init_session


# base
# ----
class ApiModel:
    """
    Base for every client model.

    A model is a handle on one collection: it holds the key that collection
    is served under, and the session it reaches the service through. The key
    arrives through the constructor rather than as a class variable, so a
    model cannot come into existence without one -- the alternative is a
    subclass that looks finished and fails at its first call instead.

    Usable directly for a resource that does not warrant a subclass:
    `ApiModel('items').all()` is the same thing `ItemModel()` names.

    Args:
        key (str) - Path segment the collection is served under, as the api
            spells it.
        session (Session) - Session to reach the service through. Left unset,
            the model uses the shared default and builds it if it has to.
    """

    def __init__(self, key, session=None):
        if not key:
            raise ValueError(f'{type(self).__name__} requires a key')

        self.key = key
        self._session = session

    def __repr__(self):
        return f'{type(self).__name__}({self.key})'

    # connection
    # ----------
    @property
    def session(self):
        """
        The session this model sends through.

        A session handed to the constructor wins. Otherwise the shared one
        is used, and built on the spot if nothing has built it yet -- which
        is what lets somebody import a model and query it with no setup call
        at all, while a model given its own session never touches the
        shared state.
        """
        return self._session or get_session() or init_session()

    # read
    # ----
    # every call checks the status before returning. an unchecked response
    # means a 404 arriving as a dict of error text and failing much later,
    # somewhere unrelated -- so a new method here must not forget it.
    def all(self):
        """
        Every member of the collection.
        """
        response = self.session.client.get(f'/{self.key}')
        response.raise_for_status()

        return response.json()

    def get(self, name):
        """
        One member of the collection, by name.

        Args:
            name (str) - Member to fetch.
        """
        if not name:
            raise ValueError('get requires a member name to fetch')

        response = self.session.client.get(f'/{self.key}/{name}')
        response.raise_for_status()

        return response.json()

    # write
    # -----
    def create(self, **fields):
        """
        Add a member to the collection.

        Args:
            fields - Fields of the member to create, sent as the json body.
        """
        response = self.session.client.post(f'/{self.key}', json=fields)
        response.raise_for_status()

        return response.json()


# models
# ------
class ItemModel(ApiModel):
    """
    The items a catalog serves.

    Args:
        session (Session) - Session to reach the service through.
    """

    def __init__(self, session=None):
        super().__init__('items', session=session)
