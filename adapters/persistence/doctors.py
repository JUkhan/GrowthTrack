"""SQLAlchemy ``Doctor`` model + repository implementation.

Current-snapshot-only table, same shape as `BrandPerformance` — no
historical rows kept; each night's run overwrites the existing row in
place. No patient health data — only the fields `entities.md` lists
(FR-5/NFR-5, Story 2.4 AC2).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import UUID, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from adapters.persistence.database import Base
from ports.doctors import DoctorRepository


class DoctorModel(Base):
    __tablename__ = "doctors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    external_doctor_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    territory: Mapped[str] = mapped_column(String, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)


class SqlAlchemyDoctorRepository(DoctorRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_many(self, rows: list[Any]) -> None:
        if not rows:
            return
        # Dedupe by conflict key (external_doctor_id), keeping the last
        # occurrence — a single multi-row ON CONFLICT DO UPDATE statement
        # raises "command cannot affect row a second time" if two input rows
        # share a key, which would otherwise crash the whole run over one
        # duplicated row.
        by_key: dict[str, Any] = {row.external_doctor_id: row for row in rows}
        values = [
            {
                "id": uuid.uuid4(),
                "external_doctor_id": row.external_doctor_id,
                "name": row.name,
                "territory": row.territory,
                "priority": row.priority,
            }
            for row in by_key.values()
        ]
        stmt = insert(DoctorModel).values(values)
        # on_conflict_do_update, not _do_nothing: a re-run must refresh the
        # snapshot in place.
        stmt = stmt.on_conflict_do_update(
            index_elements=["external_doctor_id"],
            set_={
                "name": stmt.excluded.name,
                "territory": stmt.excluded.territory,
                "priority": stmt.excluded.priority,
            },
        )
        await self._session.execute(stmt)
