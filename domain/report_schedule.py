"""Daily Report send-time schedule (Story 4.4, AD-11).

Unlike ``domain/preferences.py``'s ``UserPreferenceService``, every write
here is audit-logged — AD-7/FR-12 explicitly lists "Daily Report schedule
changes" in the audited action set (already called out in
``domain/preferences.py``'s own docstring as a forward reference to this
story).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from domain.models import AuditLogEntry, ReportSchedule
from ports.audit import AuditLogRepository
from ports.settings import ReportScheduleRepository


class InvalidScheduleFields(Exception):
    """Raised when send_hour_utc/send_minute_utc are out of range — defense
    in depth. The API layer does the Asia/Dhaka->UTC conversion and should
    itself never produce an out-of-range value, but the domain layer must
    not trust that."""


class ReportScheduleService:
    def __init__(self, schedules: ReportScheduleRepository, audit_log: AuditLogRepository) -> None:
        self._schedules = schedules
        self._audit_log = audit_log

    async def get_schedule(self) -> ReportSchedule:
        return await self._schedules.get()

    async def update_schedule(
        self, send_hour_utc: int, send_minute_utc: int, actor_user_id: uuid.UUID
    ) -> ReportSchedule:
        if not (0 <= send_hour_utc <= 23) or not (0 <= send_minute_utc <= 59):
            raise InvalidScheduleFields()

        updated = await self._schedules.update(
            send_hour_utc, send_minute_utc, actor_user_id, datetime.now(UTC)
        )
        await self._audit_log.add(
            AuditLogEntry(
                id=uuid.uuid4(),
                actor_user_id=actor_user_id,
                action="report_schedule.updated",
                entity_type="ReportSchedule",
                entity_id=updated.id,
                details={"send_hour_utc": send_hour_utc, "send_minute_utc": send_minute_utc},
                created_at=updated.updated_at,
            )
        )
        return updated
