"""SQLAlchemy ``SalesData`` model + repository implementation.

``SalesData`` is a growing time series (Dashboard's YTD/MTD needs every
past day's row) — unique on ``(date, team_id)``; a nightly run only ever
inserts/updates *today's* row, it never touches historical dates.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, ForeignKey, Numeric, UniqueConstraint, func, select
from sqlalchemy.dialects.postgresql import UUID, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from adapters.persistence.database import Base
from domain.models import SalesData
from ports.sales_data import SalesDataRepository


class SalesDataModel(Base):
    __tablename__ = "sales_data"
    __table_args__ = (UniqueConstraint("date", "team_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False
    )
    sales_amount: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    achievement_pct: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    growth_pct: Mapped[Decimal] = mapped_column(Numeric, nullable=False)


class SqlAlchemySalesDataRepository(SalesDataRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_many(self, rows: list[Any]) -> None:
        if not rows:
            return
        # Dedupe by conflict key (date, team_id), keeping the last occurrence
        # — a single multi-row ON CONFLICT DO UPDATE statement raises "command
        # cannot affect row a second time" if two input rows share a key,
        # which would otherwise crash the whole run over one duplicated row.
        by_key: dict[tuple, Any] = {(row.date, row.team_id): row for row in rows}
        values = [
            {
                "id": uuid.uuid4(),
                "date": row.date,
                "team_id": row.team_id,
                "sales_amount": row.sales_amount,
                "achievement_pct": row.achievement_pct,
                "growth_pct": row.growth_pct,
            }
            for row in by_key.values()
        ]
        stmt = insert(SalesDataModel).values(values)
        # on_conflict_do_update, not _do_nothing: a re-run of the same
        # night's import (or a corrected re-import) must refresh values.
        stmt = stmt.on_conflict_do_update(
            index_elements=["date", "team_id"],
            set_={
                "sales_amount": stmt.excluded.sales_amount,
                "achievement_pct": stmt.excluded.achievement_pct,
                "growth_pct": stmt.excluded.growth_pct,
            },
        )
        await self._session.execute(stmt)

    async def sum_amount_in_range(self, start_date: date, end_date: date) -> Decimal:
        # COALESCE is required because SQL SUM over zero rows is NULL, not
        # 0 — returning None here would break the dashboard's arithmetic.
        stmt = select(func.coalesce(func.sum(SalesDataModel.sales_amount), 0)).where(
            SalesDataModel.date >= start_date, SalesDataModel.date <= end_date
        )
        result = await self._session.execute(stmt)
        return Decimal(result.scalar_one())

    async def latest_per_team(self) -> list[Any]:
        # Postgres DISTINCT ON idiom for "latest row per group" — avoids an
        # N+1 Python loop over teams.
        stmt = select(SalesDataModel).distinct(SalesDataModel.team_id).order_by(
            SalesDataModel.team_id, SalesDataModel.date.desc()
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars().all()]

    @staticmethod
    def _to_domain(row: SalesDataModel) -> SalesData:
        return SalesData(
            id=row.id,
            date=row.date,
            team_id=row.team_id,
            sales_amount=row.sales_amount,
            achievement_pct=row.achievement_pct,
            growth_pct=row.growth_pct,
        )
