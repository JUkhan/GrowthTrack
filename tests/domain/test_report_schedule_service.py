import uuid
from datetime import UTC, datetime

import pytest

from domain.models import AuditLogEntry, ReportSchedule
from domain.report_schedule import InvalidScheduleFields, ReportScheduleService

REPORT_SCHEDULE_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class FakeReportScheduleRepository:
    def __init__(self, schedule: ReportSchedule | None = None) -> None:
        self._schedule = schedule or ReportSchedule(
            id=REPORT_SCHEDULE_ID,
            send_hour_utc=1,
            send_minute_utc=0,
            updated_at=datetime.now(UTC),
            updated_by_user_id=None,
        )
        self.update_calls: list[tuple] = []

    async def get(self) -> ReportSchedule:
        return self._schedule

    async def update(
        self,
        send_hour_utc: int,
        send_minute_utc: int,
        updated_by_user_id: uuid.UUID,
        updated_at: datetime,
    ) -> ReportSchedule:
        self.update_calls.append((send_hour_utc, send_minute_utc, updated_by_user_id, updated_at))
        self._schedule = ReportSchedule(
            id=self._schedule.id,
            send_hour_utc=send_hour_utc,
            send_minute_utc=send_minute_utc,
            updated_at=updated_at,
            updated_by_user_id=updated_by_user_id,
        )
        return self._schedule


class FakeAuditLogRepository:
    def __init__(self) -> None:
        self.entries: list[AuditLogEntry] = []

    async def add(self, entry: AuditLogEntry) -> None:
        self.entries.append(entry)


def _service(schedule: ReportSchedule | None = None) -> tuple[
    ReportScheduleService, FakeReportScheduleRepository, FakeAuditLogRepository
]:
    schedules = FakeReportScheduleRepository(schedule)
    audit_log = FakeAuditLogRepository()
    return ReportScheduleService(schedules, audit_log), schedules, audit_log


async def test_get_schedule_returns_the_repos_row_unchanged():
    schedule = ReportSchedule(
        id=REPORT_SCHEDULE_ID,
        send_hour_utc=3,
        send_minute_utc=30,
        updated_at=datetime.now(UTC),
        updated_by_user_id=None,
    )
    service, _, _ = _service(schedule)

    result = await service.get_schedule()

    assert result == schedule


async def test_update_schedule_with_valid_values_calls_the_repo_and_writes_one_audit_entry():
    service, schedules, audit_log = _service()
    actor_id = uuid.uuid4()

    updated = await service.update_schedule(
        send_hour_utc=9, send_minute_utc=45, actor_user_id=actor_id
    )

    assert updated.send_hour_utc == 9
    assert updated.send_minute_utc == 45
    assert len(schedules.update_calls) == 1

    assert len(audit_log.entries) == 1
    entry = audit_log.entries[0]
    assert entry.action == "report_schedule.updated"
    assert entry.entity_type == "ReportSchedule"
    assert entry.entity_id == REPORT_SCHEDULE_ID
    assert entry.actor_user_id == actor_id
    assert entry.details == {"send_hour_utc": 9, "send_minute_utc": 45}


@pytest.mark.parametrize(
    "send_hour_utc,send_minute_utc",
    [(24, 0), (-1, 0), (0, 60), (0, -1)],
)
async def test_update_schedule_with_out_of_range_values_raises_without_touching_repo_or_audit(
    send_hour_utc, send_minute_utc
):
    service, schedules, audit_log = _service()

    with pytest.raises(InvalidScheduleFields):
        await service.update_schedule(
            send_hour_utc=send_hour_utc,
            send_minute_utc=send_minute_utc,
            actor_user_id=uuid.uuid4(),
        )

    assert schedules.update_calls == []
    assert audit_log.entries == []
