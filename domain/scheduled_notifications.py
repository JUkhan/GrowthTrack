"""Automated Daily Report generation & send (Story 4.2, CAP-3, FR-6).

Lateral extension of Story 4.1's already-built hexagonal slice —
``Notification``/``NotificationDelivery``/``MessageTemplate`` domain
types, ports, adapters, and both AD-2 partial unique indexes already
exist and already support ``notification_type=scheduled``. The genuinely
new work here is: an advisory-lock + unique-index-catch idempotency path
distinct from Manual's picker-driven flow, Daily Report content assembly
(``domain/daily_report.py``), and this orchestration.

Not audit-logged, same reasoning as ``domain/ingestion.py``'s nightly
import: a Scheduled run has no human actor (AD-7 governs administrative
actions, not background jobs) — structured logging with a per-run
``correlation_id`` is used instead.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from domain.daily_report import DailyReportContentService
from domain.models import (
    DeliveryStatus,
    Notification,
    NotificationDelivery,
    NotificationType,
    UserStatus,
)
from domain.notifications import RecipientResolutionService, dispatch_deliveries
from ports.notifications import (
    MessageTemplateRepository,
    NotificationDeliveryRepository,
    NotificationRepository,
)
from ports.users import UserRepository
from ports.whatsapp import WhatsAppSender

logger = logging.getLogger(__name__)

# The demo/seed-provisioned MessageTemplate this service looks up by name
# (scripts/seed_demo_data.py seeds this row — Task 6).
DAILY_REPORT_TEMPLATE_NAME = "Daily Report"

# The only content-variable names run_daily_report ever assembles a value
# for (see values_by_slot_name below). Story 4.5's generic
# MessageTemplateDirectoryService.update_template has no awareness that a
# template named "Daily Report" carries this specific contract — an
# Administrator editing this template's variable_slots to any name outside
# this set would otherwise raise an uncaught KeyError and abort the whole
# run (code review).
_KNOWN_CONTENT_VARIABLE_SLOTS = frozenset(
    {
        "ytd_sales",
        "mtd_sales",
        "achievement_pct",
        "growth_pct",
        "team_performance",
        "top_brand",
        "focus_brand",
        "top_doctors",
    }
)


class ScheduledReportOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    # Mirrors domain/ingestion.py's ImportOutcome.SKIPPED naming/semantics —
    # covers: another run already holds the advisory lock, zero eligible
    # recipients, the Daily Report template isn't provisioned, or a
    # same-day duplicate run caught by AD-2's partial unique index. None
    # of these are errors; all are expected, loggable no-ops.
    SKIPPED = "skipped"


@dataclass
class ScheduledReportResult:
    outcome: ScheduledReportOutcome
    notification_id: uuid.UUID | None = None
    recipient_count: int = 0


class ScheduledReportService:
    def __init__(
        self,
        notifications: NotificationRepository,
        deliveries: NotificationDeliveryRepository,
        templates: MessageTemplateRepository,
        users: UserRepository,
        resolution: RecipientResolutionService,
        content: DailyReportContentService,
        whatsapp: WhatsAppSender,
        max_retry_attempts: int,
    ) -> None:
        self._notifications = notifications
        self._deliveries = deliveries
        self._templates = templates
        self._users = users
        self._resolution = resolution
        self._content = content
        self._whatsapp = whatsapp
        self._max_retry_attempts = max_retry_attempts

    async def run_daily_report(self, today: date, now: datetime) -> ScheduledReportResult:
        # Defense-in-depth against two overlapping scheduler
        # processes/threads — narrows the concurrency window; AD-2's
        # partial unique index (caught below) is the authoritative
        # zero-duplicate-send guarantee for the wider restart/misfire case
        # this lock alone can't cover.
        if not await self._notifications.try_acquire_daily_report_lock():
            logger.info("scheduled report already running, skipping")
            return ScheduledReportResult(outcome=ScheduledReportOutcome.SKIPPED)

        all_users = await self._users.list_all()
        active_users = [user for user in all_users if user.status == UserStatus.ACTIVE]
        # Reuses AD-2's one shared resolution function — every active User
        # is already passed individually, so team_ids/recipient_list_ids
        # are correctly empty (no Team/RecipientList expansion applies).
        resolved = await self._resolution.resolve(
            user_ids=[user.id for user in active_users], team_ids=[], recipient_list_ids=[]
        )
        if resolved.unique_count == 0:
            logger.warning("zero eligible recipients for scheduled daily report")
            return ScheduledReportResult(outcome=ScheduledReportOutcome.SKIPPED)

        company_wide = await self._content.build_company_wide_content(today, now)

        template = await self._templates.get_by_name(DAILY_REPORT_TEMPLATE_NAME)
        if template is None:
            logger.error("Daily Report message template not provisioned, skipping scheduled send")
            return ScheduledReportResult(outcome=ScheduledReportOutcome.SKIPPED)
        unknown_slots = set(template.variable_slots) - _KNOWN_CONTENT_VARIABLE_SLOTS
        if unknown_slots:
            logger.error(
                "Daily Report message template has unrecognized variable_slots, skipping "
                "scheduled send",
                extra={"unknown_slots": sorted(unknown_slots)},
            )
            return ScheduledReportResult(outcome=ScheduledReportOutcome.SKIPPED)

        notification = Notification(
            id=uuid.uuid4(),
            notification_type=NotificationType.SCHEDULED,
            template_id=template.id,
            created_at=now,
            created_by_user_id=None,
        )
        # Empty targets list — a Scheduled Notification has no picker
        # selections to record (unlike Manual's raw user/team/list picks).
        await self._notifications.add(notification, [])

        # Computed before delivery_rows below (rather than after
        # bulk_create, as originally structured) so each row's
        # content_variables can be persisted at creation time — a retry
        # needs the exact per-recipient values this row was composed with,
        # and nothing else stores them (Story 4.3).
        recipients_by_id = {
            user.id: user
            for user in await self._users.get_many_by_ids(resolved.recipient_user_ids)
        }
        territory_by_recipient = await self._content.resolve_territories(
            list(recipients_by_id.values())
        )

        # build_doctor_section is called once per *distinct* territory
        # represented among this run's resolved recipients, not once per
        # recipient — several recipients typically share one Team/territory.
        doctor_section_by_territory: dict[str, str] = {}
        content_variables_by_recipient: dict[uuid.UUID, dict[str, str]] = {}
        for recipient_user_id in resolved.recipient_user_ids:
            territory = territory_by_recipient.get(recipient_user_id)
            if territory is None:
                # Recipient vanished between resolve() and the
                # get_many_by_ids() call above (e.g. deleted mid-run,
                # possible under Postgres's default READ COMMITTED
                # isolation) — no content_variables entry is built for
                # them; dispatch_deliveries' own recipients_by_id.get(...)
                # check (domain/notifications.py) already fails this
                # recipient's delivery row gracefully rather than
                # aborting the whole run.
                continue
            if territory not in doctor_section_by_territory:
                doctor_section_by_territory[territory] = await self._content.build_doctor_section(
                    territory
                )
            values_by_slot_name = {
                "ytd_sales": company_wide.ytd_sales,
                "mtd_sales": company_wide.mtd_sales,
                "achievement_pct": company_wide.achievement_pct,
                "growth_pct": company_wide.growth_pct,
                "team_performance": company_wide.team_performance,
                "top_brand": company_wide.top_brand,
                "focus_brand": company_wide.focus_brand,
                "top_doctors": doctor_section_by_territory[territory],
            }
            # Positional string keys ("1", "2", ...), same convention as
            # ManualNotificationService.compose_and_send.
            content_variables_by_recipient[recipient_user_id] = {
                str(index): values_by_slot_name[slot]
                for index, slot in enumerate(template.variable_slots, start=1)
            }

        delivery_rows = [
            NotificationDelivery(
                id=uuid.uuid4(),
                notification_id=notification.id,
                notification_type=NotificationType.SCHEDULED,
                recipient_user_id=recipient_user_id,
                operational_day=today,
                status=DeliveryStatus.QUEUED,
                attempt_count=0,
                provider_message_sid=None,
                failure_reason=None,
                created_at=now,
                updated_at=now,
                content_variables=content_variables_by_recipient.get(recipient_user_id, {}),
            )
            for recipient_user_id in resolved.recipient_user_ids
        ]
        try:
            await self._deliveries.bulk_create(delivery_rows)
        except Exception:
            # Broad on purpose, mirroring domain/ingestion.py's own
            # top-level `except Exception` precedent: AD-1 forbids domain
            # from importing sqlalchemy, so this can't name
            # sqlalchemy.exc.IntegrityError directly. This call site's
            # only expected failure is a same-day duplicate run that
            # slipped past the advisory lock above (e.g. a scheduler
            # restart between the lock's commit and a cron misfire
            # re-trigger) hitting AD-2's partial unique index — not a
            # stand-in for error handling anywhere else in this method.
            logger.info(
                "scheduled report already sent for operational_day, skipping",
                extra={"operational_day": today.isoformat()},
            )
            return ScheduledReportResult(outcome=ScheduledReportOutcome.SKIPPED)

        outcomes = await dispatch_deliveries(
            deliveries=self._deliveries,
            whatsapp=self._whatsapp,
            delivery_rows=delivery_rows,
            content_variables_by_recipient=content_variables_by_recipient,
            template_content_sid=template.twilio_content_sid,
            recipients_by_id=recipients_by_id,
            max_retry_attempts=self._max_retry_attempts,
        )

        # The Dev Notes' stated auditability mechanism for a Scheduled run
        # (structured logging instead of an audit-log entry) needs an
        # actual outcome summary logged somewhere — without this, nothing
        # records whether a run's dispatch step (e.g. a full Twilio
        # outage) actually succeeded (code review). Counts both terminal
        # FAILED and still-retryable FAILED_RETRYABLE outcomes (Story
        # 4.3) — either way, that recipient didn't cleanly reach SENDING
        # this run.
        failed_count = sum(
            1
            for outcome in outcomes
            if outcome.status in (DeliveryStatus.FAILED, DeliveryStatus.FAILED_RETRYABLE)
        )
        logger.info(
            "scheduled daily report dispatch complete",
            extra={
                "notification_id": str(notification.id),
                "recipient_count": resolved.unique_count,
                "failed_count": failed_count,
            },
        )

        return ScheduledReportResult(
            outcome=ScheduledReportOutcome.SUCCEEDED,
            notification_id=notification.id,
            recipient_count=resolved.unique_count,
        )
