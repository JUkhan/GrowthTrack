"""SQLAlchemy engine/session wiring shared by the runtime app and Alembic.

``Base`` is the single declarative base every ORM model (added by later
stories) registers against, so Alembic autogenerate sees the full schema.
"""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from config import get_settings


class Base(DeclarativeBase):
    pass


def create_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
