from sqlalchemy import select
from sqlalchemy.orm import Session

from catalog.db.models import Item


def list_items(session: Session) -> list[Item]:
    statement = select(Item).order_by(Item.id)
    return list(session.scalars(statement))


def get_item(session: Session, name: str) -> Item | None:
    statement = select(Item).where(Item.name == name)
    return session.scalar(statement)


def create_item(
    session: Session,
    name: str,
    desc: str | None,
    tags: list[str],
) -> Item:
    item = Item(
        name=name,
        desc=desc,
        tags=tags,
    )

    session.add(item)
    session.commit()
    session.refresh(item)

    return item
