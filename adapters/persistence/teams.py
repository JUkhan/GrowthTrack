"""SQLAlchemy ``Team`` model + repository implementation.

Full CRUD (soft-delete status, optimistic-concurrency version column) added
by Epic 3 Story 3.1, on top of the `id`/`name` columns Story 2.1 created to
satisfy the FK from `SalesData`.
"""

from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy import Integer, String, select, text, update
from sqlalchemy.dialects.postgresql import UUID, insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from adapters.persistence.database import Base
from domain.models import Team, TeamStatus
from ports.teams import TeamRepository


class TeamModel(Base):
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    # Uniqueness enforced by a partial index (ix_teams_name_active_uq,
    # WHERE status = 'active') rather than a column-level constraint — a
    # soft-deleted Team's name is reusable by a new Team (code review of
    # Story 3.1, migration 17eb25555c26).
    name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


def _to_domain(row: TeamModel) -> Team:
    return Team(id=row.id, name=row.name, status=TeamStatus(row.status), version=row.version)


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
        # status/version are omitted here on purpose — Postgres fills them
        # from the column default (Story 3.1's migration set
        # server_default), so this ingestion-only path (Story 2.1) stays
        # untouched by Story 3.1's directory-CRUD additions below.
        #
        # index_where matches ix_teams_name_active_uq, the partial unique
        # index code review of Story 3.1 (migration 17eb25555c26) scoped to
        # active rows only — this INSERT always creates an active row, so
        # the conflict target must name that same partial index, not a
        # (now nonexistent) plain unique constraint on name.
        stmt = insert(TeamModel).values(id=uuid.uuid4(), name=name)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["name"], index_where=text("status = 'active'")
        )
        await self._session.execute(stmt)

        # Status-filtered to match the partial index above: an inactive row
        # with the same (now-reusable) name can coexist with the active row
        # this call just inserted or found, and an unfiltered lookup would
        # return both, raising MultipleResultsFound.
        result = await self._session.execute(
            select(TeamModel.id).where(
                TeamModel.name == name, TeamModel.status == TeamStatus.ACTIVE.value
            )
        )
        return result.scalar_one()

    async def list_all(self) -> list[tuple[uuid.UUID, str]]:
        stmt = select(TeamModel.id, TeamModel.name).order_by(TeamModel.name)
        result = await self._session.execute(stmt)
        return [(row.id, row.name) for row in result.all()]

    async def add(self, team_id: uuid.UUID, name: str) -> None:
        self._session.add(TeamModel(id=team_id, name=name, status="active", version=1))

    async def get_by_id(self, team_id: uuid.UUID) -> Team | None:
        row = await self._session.get(TeamModel, team_id)
        return _to_domain(row) if row is not None else None

    async def get_by_name(self, name: str) -> Team | None:
        # Active-only (code review of Story 3.1): a soft-deleted Team's
        # name is reusable, matching ix_teams_name_active_uq.
        stmt = select(TeamModel).where(
            TeamModel.name == name, TeamModel.status == TeamStatus.ACTIVE.value
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def list_all_full(self) -> list[Team]:
        stmt = select(TeamModel).order_by(TeamModel.name)
        result = await self._session.execute(stmt)
        return [_to_domain(row) for row in result.scalars().all()]

    async def update_name(self, team_id: uuid.UUID, name: str, expected_version: int) -> bool:
        stmt = (
            update(TeamModel)
            .where(TeamModel.id == team_id, TeamModel.version == expected_version)
            .values(name=name, version=TeamModel.version + 1)
        )
        result = cast(CursorResult, await self._session.execute(stmt))
        return result.rowcount > 0

    async def deactivate(self, team_id: uuid.UUID) -> None:
        stmt = (
            update(TeamModel)
            .where(TeamModel.id == team_id)
            .values(status=TeamStatus.INACTIVE.value, version=TeamModel.version + 1)
        )
        await self._session.execute(stmt)
