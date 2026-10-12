# -*- coding: utf-8 -*-
"""

    API endpoints for managing items.

    Storage is a module-level dict, so writes are visible only to the process
    that made them and are lost on restart. That is deliberate: catalog exists
    to be a realistic thing to put behind the gate, not a real store. The
    write endpoint is here so that authorisation has a read/write distinction
    to enforce.

"""


# imports
# -------
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from catalog.db.database import get_db
from catalog.db import repository

from catalog.logging import api as log
from catalog.server.items.schema import CreateItem, GetItem




# router
# ------
router = APIRouter(
    prefix='/items',
    tags=['items'],
    responses={404: {'description': 'Not found'}},
)

# read
# ----
@router.get('', status_code=status.HTTP_200_OK, response_model=list[GetItem])
async def list_items(session: Session = Depends(get_db)):
    """
    List every item in the catalog.
    """
    return repository.list_items(session)


@router.get('/{name}', status_code=status.HTTP_200_OK, response_model=GetItem)
async def get_item(name: str, session: Session = Depends(get_db)):
    """
    Get a single item by name.
    """
    item = repository.get_item(session, name)

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'No item named {name}',
        )

    return item


# write
# -----
@router.post('', status_code=status.HTTP_201_CREATED, response_model=GetItem)
async def create_item(payload: CreateItem, session: Session = Depends(get_db)):
    """
    Add an item to the catalog.

    Args:
        payload (CreateItem) - Item to add.
    """
    from sqlalchemy.exc import IntegrityError
    try:
        item = repository.create_item(
            session,
            name=payload.name,
            desc=payload.desc,
            tags=payload.tags,
        )
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Item {payload.name} already exists',
        )

    log.info(f'created item {item.name}')

    return item
