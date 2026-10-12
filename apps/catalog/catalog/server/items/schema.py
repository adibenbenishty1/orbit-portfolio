# -*- coding: utf-8 -*-
"""

    Data validators for items endpoints

"""


# imports
# -------
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# create
# ------
class CreateItem(BaseModel):
    """
    Payload accepted when adding an item.
    """
    name: str
    desc: Optional[str] = None
    tags: list[str] = []


# read
# ----
class GetItem(CreateItem):
    """
    Item as returned by the api, extending the create payload with the
    fields the server assigns.

    The python client subclasses this rather than restating it, so the two
    sides of the api cannot drift apart.
    """
    id: int
    created_at: datetime
