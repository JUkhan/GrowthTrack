"""SQLAlchemy ``ReportSchedule`` model + repository implementation
(Story 4.4, AD-11)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, SmallInteger, update
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from adapters.persistence.database import Base
from domain.models import REPORT_SCHEDULE_ID, ReportSchedule
from ports.settings import ReportScheduleRepository


class ReportScheduleModel(Base):
    __tablename__ = "report_schedules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    send_hour_utc: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    send_minute_utc: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


def _schedule_to_domain(row: ReportScheduleModel) -> ReportSchedule:
    return ReportSchedule(
        id=row.id,
        send_hour_utc=row.send_hour_utc,
        send_minute_utc=row.send_minute_utc,
        updated_at=row.updated_at,
        updated_by_user_id=row.updated_by_user_id,
    )


class SqlAlchemyReportScheduleRepository(ReportScheduleRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> ReportSchedule:
        # Never None in practice — the seed migration guarantees the row
        # exists; if it is somehow missing, let this raise rather than
        # silently fabricating a default, since that would hide a genuinely
        # broken deployment. An explicit check (not a bare `assert`, which
        # is stripped under `python -O`) so this guarantee holds regardless
        # of how the process is invoked.
        row = await self._session.get(ReportScheduleModel, REPORT_SCHEDULE_ID)
        if row is None:
            raise RuntimeError("report_schedules singleton row is missing")
        return _schedule_to_domain(row)

    async def update(
        self,
        send_hour_utc: int,
        send_minute_utc: int,
        updated_by_user_id: uuid.UUID,
        updated_at: datetime,
    ) -> ReportSchedule:
        stmt = (
            update(ReportScheduleModel)
            .where(ReportScheduleModel.id == REPORT_SCHEDULE_ID)
            .values(
                send_hour_utc=send_hour_utc,
                send_minute_utc=send_minute_utc,
                updated_by_user_id=updated_by_user_id,
                updated_at=updated_at,
            )
        )
        await self._session.execute(stmt)
        return await self.get()
