"""SQLAlchemy ``Team`` model + repository implementation.

``Team`` is intentionally minimal here — full CRUD (soft-delete status,
optimistic-concurrency version column, management UI) is Epic 3 Story 3.1's
job. This story creates only the `id`/`name` columns needed to satisfy the
FK from `SalesData`.
"""

from __future__ import annotations

import uuid

from sqlalchemy import String, select
from sqlalchemy.dialects.postgresql import UUID, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from adapters.persistence.database import Base
from ports.teams import TeamRepository


class TeamModel(Base):
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)


class SqlAlchemyTeamRepository(TeamRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_by_name(self, name: str) -> uuid.UUID:
        # Normalized here too (not just by callers) so this repository
        # can't be used to create two Team rows that differ only by
        # incidental leading/trailing whitespace.
        name = name.strip()
        # on_conflict_do_nothing idempotent-insert pattern (sessions.py's
        # RevokedTokenRepository.revoke precedent), followed by a SELECT to
        # return the id whether it was just inserted or already existed.
        stmt = insert(TeamModel).values(id=uuid.uuid4(), name=name)
        stmt = stmt.on_conflict_do_nothing(index_elements=["name"])
        await self._session.execute(stmt)

        result = await self._session.execute(
            select(TeamModel.id).where(TeamModel.name == name)
        )
        return result.scalar_one()
