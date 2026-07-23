"""Daily Report schedule configuration (Story 4.4, AD-11).

Unlike the webhook route (Story 4.3), this route requires the standard
``get_current_user`` Administrator-role dependency — it is a normal
authenticated portal action, not an unauthenticated provider callback.

The API boundary is where UTC (storage/domain) and Asia/Dhaka (what an
Administrator sets and sees) convert — per the epics.md Additional
Requirements' "timestamps stored/transmitted as ISO 8601 UTC, converted to
Asia/Dhaka only at presentation edges" rule, matching
``scheduler/main.py``'s existing ``astimezone(ZoneInfo("Asia/Dhaka"))``
conversion style.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence.audit_log import SqlAlchemyAuditLogRepository
from adapters.persistence.settings import SqlAlchemyReportScheduleRepository
from api.auth.dependencies import get_current_user, get_db
from domain.models import ReportSchedule, User
from domain.report_schedule import InvalidScheduleFields, ReportScheduleService

settings_router = APIRouter(prefix="/settings", tags=["settings"])

_DHAKA = ZoneInfo("Asia/Dhaka")


def _utc_to_dhaka(hour: int, minute: int) -> tuple[int, int]:
    reference = datetime(2026, 1, 1, hour, minute, tzinfo=UTC).astimezone(_DHAKA)
    return reference.hour, reference.minute


def _dhaka_to_utc(hour: int, minute: int) -> tuple[int, int]:
    reference = datetime(2026, 1, 1, hour, minute, tzinfo=_DHAKA).astimezone(UTC)
    return reference.hour, reference.minute


class ReportScheduleResponse(BaseModel):
    send_hour: int
    send_minute: int
    updated_at: datetime
    updated_by_user_id: uuid.UUID | None


class ReportScheduleWriteRequest(BaseModel):
    send_hour: int = Field(ge=0, le=23)
    send_minute: int = Field(ge=0, le=59)


def _to_response(schedule: ReportSchedule) -> ReportScheduleResponse:
    send_hour, send_minute = _utc_to_dhaka(schedule.send_hour_utc, schedule.send_minute_utc)
    return ReportScheduleResponse(
        send_hour=send_hour,
        send_minute=send_minute,
        updated_at=schedule.updated_at,
        updated_by_user_id=schedule.updated_by_user_id,
    )


def _invalid_schedule_fields() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "code": "invalid_schedule_fields",
            "message": "send_hour must be 0-23 and send_minute must be 0-59",
            "details": None,
        },
    )


@settings_router.get("/report-schedule", response_model=ReportScheduleResponse)
async def get_report_schedule(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ReportScheduleResponse:
    service = ReportScheduleService(
        SqlAlchemyReportScheduleRepository(session), SqlAlchemyAuditLogRepository(session)
    )
    schedule = await service.get_schedule()
    return _to_response(schedule)


@settings_router.patch("/report-schedule", response_model=ReportScheduleResponse)
async def update_report_schedule(
    body: ReportScheduleWriteRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ReportScheduleResponse:
    service = ReportScheduleService(
        SqlAlchemyReportScheduleRepository(session), SqlAlchemyAuditLogRepository(session)
    )
    utc_hour, utc_minute = _dhaka_to_utc(body.send_hour, body.send_minute)

    try:
        updated = await service.update_schedule(
            send_hour_utc=utc_hour, send_minute_utc=utc_minute, actor_user_id=current_user.id
        )
    except InvalidScheduleFields:
        raise _invalid_schedule_fields() from None

    await session.commit()
    return _to_response(updated)
