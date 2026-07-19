"""SQLAlchemy ``BrandPerformance`` model + repository implementation.

Current-snapshot-only table — one row per brand, no `date` column, no
historical rows kept; each night's run overwrites the existing row in
place (unlike `SalesData`, which is a growing time series).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from adapters.persistence.database import Base
from ports.brand_performance import BrandPerformanceRepository


class BrandPerformanceModel(Base):
    __tablename__ = "brand_performance"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    external_brand_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    brand_name: Mapped[str] = mapped_column(String, nullable=False)
    sales: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    growth_pct: Mapped[Decimal] = mapped_column(Numeric, nullable=False)


class SqlAlchemyBrandPerformanceRepository(BrandPerformanceRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_many(self, rows: list[Any]) -> None:
        if not rows:
            return
        # Dedupe by conflict key (external_brand_id), keeping the last
        # occurrence — a single multi-row ON CONFLICT DO UPDATE statement
        # raises "command cannot affect row a second time" if two input rows
        # share a key, which would otherwise crash the whole run over one
        # duplicated row.
        by_key: dict[str, Any] = {row.external_brand_id: row for row in rows}
        values = [
            {
                "id": uuid.uuid4(),
                "external_brand_id": row.external_brand_id,
                "brand_name": row.brand_name,
                "sales": row.sales,
                "rank": row.rank,
                "growth_pct": row.growth_pct,
            }
            for row in by_key.values()
        ]
        stmt = insert(BrandPerformanceModel).values(values)
        # on_conflict_do_update, not _do_nothing: a re-run must refresh the
        # snapshot in place.
        stmt = stmt.on_conflict_do_update(
            index_elements=["external_brand_id"],
            set_={
                "brand_name": stmt.excluded.brand_name,
                "sales": stmt.excluded.sales,
                "rank": stmt.excluded.rank,
                "growth_pct": stmt.excluded.growth_pct,
            },
        )
        await self._session.execute(stmt)
