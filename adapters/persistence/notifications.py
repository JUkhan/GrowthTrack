"""SQLAlchemy ``MessageTemplate``/``Notification``/``NotificationDelivery``
model + repository implementations (Story 4.1, CAP-4).

``notification_targets`` is mapped as its own ORM class (not a Core
``Table`` like ``recipient_list_members``) since it carries an ``id`` and a
polymorphic ``target_type``/``target_id`` pair, not a pure two-FK join row.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import cast

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, and_, or_, select, text, update
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from adapters.persistence.advisory_locks import DAILY_REPORT_LOCK_KEY
from adapters.persistence.database import Base
from config import get_settings
from domain.models import (
    DeliveryStatus,
    MessageTemplate,
    Notification,
    NotificationDelivery,
    NotificationStatusSummary,
    NotificationTarget,
    NotificationType,
)
from ports.notifications import (
    MessageTemplateRepository,
    NotificationDeliveryRepository,
    NotificationRepository,
)

logger = logging.getLogger(__name__)


class MessageTemplateModel(Base):
    __tablename__ = "message_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    twilio_content_sid: Mapped[str] = mapped_column(String, nullable=False)
    variable_slots: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    body_preview_template: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class NotificationModel(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    notification_type: Mapped[str] = mapped_column(String, nullable=False)
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("message_templates.id"), nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class NotificationTargetModel(Base):
    __tablename__ = "notification_targets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    notification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notifications.id"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String, nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)


class NotificationDeliveryModel(Base):
    __tablename__ = "notification_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    notification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notifications.id"), nullable=False
    )
    notification_type: Mapped[str] = mapped_column(String, nullable=False)
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    operational_day: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provider_message_sid: Mapped[str | None] = mapped_column(String, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_variables: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)


# Worst-status-wins ranking for the Dashboard's aggregate tile (AC #8) —
# a failure outranks anything still in-flight, which outranks a clean
# delivered outcome, mirroring DashboardPage.tsx's error > warning > neutral
# > success badge-severity ordering.
_STATUS_SEVERITY: dict[DeliveryStatus, int] = {
    DeliveryStatus.FAILED: 4,
    DeliveryStatus.FAILED_RETRYABLE: 4,
    DeliveryStatus.RETRYING: 3,
    DeliveryStatus.QUEUED: 2,
    DeliveryStatus.SENDING: 2,
    DeliveryStatus.DELIVERED: 1,
}


def _template_to_domain(row: MessageTemplateModel) -> MessageTemplate:
    return MessageTemplate(
        id=row.id,
        name=row.name,
        twilio_content_sid=row.twilio_content_sid,
        variable_slots=list(row.variable_slots),
        body_preview_template=row.body_preview_template,
        created_at=row.created_at,
    )


def _notification_to_domain(row: NotificationModel) -> Notification:
    return Notification(
        id=row.id,
        notification_type=NotificationType(row.notification_type),
        template_id=row.template_id,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
    )


def _delivery_to_domain(row: NotificationDeliveryModel) -> NotificationDelivery:
    return NotificationDelivery(
        id=row.id,
        notification_id=row.notification_id,
        notification_type=NotificationType(row.notification_type),
        recipient_user_id=row.recipient_user_id,
        operational_day=row.operational_day,
        status=DeliveryStatus(row.status),
        attempt_count=row.attempt_count,
        provider_message_sid=row.provider_message_sid,
        failure_reason=row.failure_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
        content_variables=dict(row.content_variables),
    )


class SqlAlchemyMessageTemplateRepository(MessageTemplateRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active(self) -> list[MessageTemplate]:
        # No pagination (Dev Notes: consistent with the existing
        # directory-listing convention) and no status column yet — every
        # row in this table is a usable template.
        stmt = select(MessageTemplateModel).order_by(MessageTemplateModel.name)
        result = await self._session.execute(stmt)
        return [_template_to_domain(row) for row in result.scalars().all()]

    async def get_by_id(self, template_id: uuid.UUID) -> MessageTemplate | None:
        row = await self._session.get(MessageTemplateModel, template_id)
        return _template_to_domain(row) if row is not None else None

    async def get_by_name(self, name: str) -> MessageTemplate | None:
        stmt = select(MessageTemplateModel).where(MessageTemplateModel.name == name)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _template_to_domain(row) if row is not None else None

    async def add(self, template: MessageTemplate) -> None:
        self._session.add(
            MessageTemplateModel(
                id=template.id,
                name=template.name,
                twilio_content_sid=template.twilio_content_sid,
                variable_slots=template.variable_slots,
                body_preview_template=template.body_preview_template,
                created_at=template.created_at,
            )
        )

    async def update(
        self,
        template_id: uuid.UUID,
        name: str,
        twilio_content_sid: str,
        variable_slots: list[str],
        body_preview_template: str,
    ) -> bool:
        stmt = (
            update(MessageTemplateModel)
            .where(MessageTemplateModel.id == template_id)
            .values(
                name=name,
                twilio_content_sid=twilio_content_sid,
                variable_slots=variable_slots,
                body_preview_template=body_preview_template,
            )
        )
        result = cast(CursorResult, await self._session.execute(stmt))
        return result.rowcount > 0


class SqlAlchemyNotificationRepository(NotificationRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, notification: Notification, targets: list[NotificationTarget]) -> None:
        self._session.add(
            NotificationModel(
                id=notification.id,
                notification_type=notification.notification_type.value,
                template_id=notification.template_id,
                created_by_user_id=notification.created_by_user_id,
                created_at=notification.created_at,
            )
        )
        for target in targets:
            self._session.add(
                NotificationTargetModel(
                    id=target.id,
                    notification_id=target.notification_id,
                    target_type=target.target_type.value,
                    target_id=target.target_id,
                )
            )
        # Flushed immediately: the caller follows this with a bulk_create of
        # NotificationDelivery rows carrying a FK to this not-yet-flushed
        # notification_id, same reasoning as RecipientListRepository.add().
        await self._session.flush()

    async def try_acquire_daily_report_lock(self) -> bool:
        # Same pg_try_advisory_xact_lock pattern as
        # SqlAlchemyImportRunRepository.try_acquire_lock — non-blocking,
        # transaction-scoped, no separate release call needed.
        result = await self._session.execute(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": DAILY_REPORT_LOCK_KEY}
        )
        return bool(result.scalar())

    async def get_by_id(self, notification_id: uuid.UUID) -> Notification | None:
        row = await self._session.get(NotificationModel, notification_id)
        return _notification_to_domain(row) if row is not None else None


class SqlAlchemyNotificationDeliveryRepository(NotificationDeliveryRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bulk_create(self, rows: list[NotificationDelivery]) -> None:
        for row in rows:
            self._session.add(
                NotificationDeliveryModel(
                    id=row.id,
                    notification_id=row.notification_id,
                    notification_type=row.notification_type.value,
                    recipient_user_id=row.recipient_user_id,
                    operational_day=row.operational_day,
                    status=row.status.value,
                    attempt_count=row.attempt_count,
                    provider_message_sid=row.provider_message_sid,
                    failure_reason=row.failure_reason,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                    content_variables=row.content_variables,
                )
            )
        try:
            await self._session.flush()
        except IntegrityError:
            # A same-day duplicate scheduled run (AD-2's partial unique
            # index on (recipient_user_id, operational_day)) lands here.
            # A failed flush leaves the session's transaction unusable for
            # any further statement — including the caller's eventual
            # commit — until it's rolled back (same hazard
            # SqlAlchemyImportRunRepository.mark_failed already rolls back
            # for, Story 2.1). Roll back here, at the layer that actually
            # knows about SQLAlchemy/Postgres transaction semantics (AD-1
            # keeps this out of domain/), then re-raise so the caller's
            # own except-Exception branch still sees and handles the
            # duplicate.
            await self._session.rollback()
            raise

    async def claim_for_dispatch(self, delivery_id: uuid.UUID) -> bool:
        stmt = (
            update(NotificationDeliveryModel)
            .where(
                NotificationDeliveryModel.id == delivery_id,
                NotificationDeliveryModel.status.in_(
                    [DeliveryStatus.QUEUED.value, DeliveryStatus.FAILED_RETRYABLE.value]
                ),
            )
            .values(status=DeliveryStatus.SENDING.value, updated_at=_now())
        )
        result = cast(CursorResult, await self._session.execute(stmt))
        return result.rowcount > 0

    async def update_after_send(
        self,
        delivery_id: uuid.UUID,
        status: DeliveryStatus,
        provider_message_sid: str | None,
        failure_reason: str | None,
    ) -> None:
        stmt = (
            update(NotificationDeliveryModel)
            .where(NotificationDeliveryModel.id == delivery_id)
            .values(
                status=status.value,
                provider_message_sid=provider_message_sid,
                failure_reason=failure_reason,
                attempt_count=NotificationDeliveryModel.attempt_count + 1,
                updated_at=_now(),
            )
        )
        await self._session.execute(stmt)

    async def get_by_provider_message_sid(self, sid: str) -> NotificationDelivery | None:
        stmt = select(NotificationDeliveryModel).where(
            NotificationDeliveryModel.provider_message_sid == sid
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        if not rows:
            return None
        if len(rows) > 1:
            # No DB uniqueness constraint backs the "current SID is unique
            # per row" invariant this lookup relies on. If it's ever
            # violated, treat it the same as an unmatched SID (superseded)
            # rather than raising — a routine Twilio callback must never
            # 500.
            logger.warning(
                "multiple NotificationDelivery rows share provider_message_sid",
                extra={"provider_message_sid": sid, "row_count": len(rows)},
            )
            return None
        return _delivery_to_domain(rows[0])

    async def update_status_from_webhook(
        self, delivery_id: uuid.UUID, status: DeliveryStatus, failure_reason: str | None
    ) -> None:
        stmt = (
            update(NotificationDeliveryModel)
            .where(NotificationDeliveryModel.id == delivery_id)
            .values(status=status.value, failure_reason=failure_reason, updated_at=_now())
        )
        await self._session.execute(stmt)

    async def list_retry_eligible(self, now: datetime) -> list[NotificationDelivery]:
        settings = get_settings()
        backoff_minutes_by_attempt = {
            1: settings.notification_retry_backoff_minutes_1,
            2: settings.notification_retry_backoff_minutes_2,
            3: settings.notification_retry_backoff_minutes_3,
        }
        stmt = select(NotificationDeliveryModel).where(
            NotificationDeliveryModel.status == DeliveryStatus.FAILED_RETRYABLE.value,
            or_(
                *[
                    and_(
                        NotificationDeliveryModel.attempt_count == attempt_count,
                        NotificationDeliveryModel.updated_at <= now - timedelta(minutes=minutes),
                    )
                    for attempt_count, minutes in backoff_minutes_by_attempt.items()
                ]
            ),
        )
        result = await self._session.execute(stmt)
        return [_delivery_to_domain(row) for row in result.scalars().all()]

    async def most_recent_status_summary(self) -> NotificationStatusSummary | None:
        latest_id_stmt = (
            select(NotificationModel.id).order_by(NotificationModel.created_at.desc()).limit(1)
        )
        latest_id_result = await self._session.execute(latest_id_stmt)
        notification_id = latest_id_result.scalar_one_or_none()
        if notification_id is None:
            return None

        rows_stmt = select(NotificationDeliveryModel).where(
            NotificationDeliveryModel.notification_id == notification_id
        )
        rows_result = await self._session.execute(rows_stmt)
        rows = rows_result.scalars().all()
        if not rows:
            return None

        worst = max(
            rows,
            key=lambda row: (_STATUS_SEVERITY[DeliveryStatus(row.status)], row.updated_at),
        )
        return NotificationStatusSummary(
            status=DeliveryStatus(worst.status),
            updated_at=max(row.updated_at for row in rows),
        )


def _now() -> datetime:
    return datetime.now(UTC)
