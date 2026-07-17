"""SQLAlchemy revocation-record model + repository implementation (AD-8)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import UUID, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from adapters.persistence.database import Base
from ports.sessions import RevokedTokenRepository


class RevokedTokenModel(Base):
    __tablename__ = "revoked_tokens"

    jti: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SqlAlchemyRevokedTokenRepository(RevokedTokenRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def revoke(self, jti: uuid.UUID, revoked_at: datetime) -> None:
        # on_conflict_do_nothing makes this idempotent: two concurrent
        # logout requests racing on the same jti (e.g. two tabs sharing a
        # session) would otherwise have the losing commit raise
        # IntegrityError on the jti primary key.
        stmt = insert(RevokedTokenModel).values(jti=jti, revoked_at=revoked_at)
        stmt = stmt.on_conflict_do_nothing(index_elements=["jti"])
        await self._session.execute(stmt)

    async def is_revoked(self, jti: uuid.UUID) -> bool:
        return await self._session.get(RevokedTokenModel, jti) is not None
