"""Scheduler process entrypoint (inbound adapter, AD-5).

A separate container from ``api/`` so a web-tier crash or redeploy never
silently drops a scheduled run. Runs its own in-process APScheduler
(AD-2) — no Redis/Celery in Phase 1.
"""

import asyncio
import json
import logging
import pathlib
import signal
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

from adapters.persistence.brand_performance import SqlAlchemyBrandPerformanceRepository
from adapters.persistence.consent import SqlAlchemyOptInConsentRepository
from adapters.persistence.database import create_session_factory
from adapters.persistence.doctors import SqlAlchemyDoctorRepository
from adapters.persistence.import_runs import SqlAlchemyImportRunRepository
from adapters.persistence.notifications import (
    SqlAlchemyMessageTemplateRepository,
    SqlAlchemyNotificationDeliveryRepository,
    SqlAlchemyNotificationRepository,
)
from adapters.persistence.recipient_lists import SqlAlchemyRecipientListRepository
from adapters.persistence.sales_data import SqlAlchemySalesDataRepository
from adapters.persistence.settings import SqlAlchemyReportScheduleRepository
from adapters.persistence.staging import SqlAlchemyStagingRepository
from adapters.persistence.teams import SqlAlchemyTeamRepository
from adapters.persistence.users import SqlAlchemyUserRepository
from adapters.source_system.csv_importer import CsvFileSourceSystemImporter
from adapters.whatsapp_twilio.sender import TwilioWhatsAppSender
from config import get_settings
from domain.daily_report import DailyReportContentService
from domain.ingestion import SourceSystemImportService
from domain.metrics import BrandPerformanceService, DashboardMetricsService, DoctorVisitListService
from domain.models import ReportSchedule
from domain.notifications import RecipientResolutionService, dispatch_deliveries
from domain.scheduled_notifications import ScheduledReportService

_RESERVED_LOG_RECORD_FIELDS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
}


class _JsonFormatter(logging.Formatter):
    """Renders every log line as JSON, including ``extra={...}`` fields —
    the nightly import job's per-run ``correlation_id`` and per-row
    rejection details (AC #3) need to be machine-parseable, not just
    human-readable text."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key not in _RESERVED_LOG_RECORD_FIELDS:
                payload[key] = value
        return json.dumps(payload, default=str)


def _configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler])


logger = logging.getLogger(__name__)

HEARTBEAT_PATH = pathlib.Path("/tmp/scheduler.heartbeat")


def _heartbeat() -> None:
    HEARTBEAT_PATH.touch()


def _run_nightly_import() -> None:
    try:
        asyncio.run(_run_nightly_import_async())
    except Exception:
        logger.exception("nightly import job crashed")  # never let this kill the scheduler process


async def _run_nightly_import_async() -> None:
    session_factory = create_session_factory()
    async with session_factory() as session:
        service = SourceSystemImportService(
            importer=CsvFileSourceSystemImporter(get_settings().source_system_import_dir),
            staging=SqlAlchemyStagingRepository(session),
            teams=SqlAlchemyTeamRepository(session),
            sales_data=SqlAlchemySalesDataRepository(session),
            brand_performance=SqlAlchemyBrandPerformanceRepository(session),
            doctors=SqlAlchemyDoctorRepository(session),
            import_runs=SqlAlchemyImportRunRepository(session),
        )
        await service.run()
        await session.commit()


def _should_run_daily_report(now: datetime, schedule: ReportSchedule) -> bool:
    """Pure, directly-testable boundary check: has today's UTC target time
    (the ReportSchedule row's own already-UTC hour/minute) arrived yet?
    Written as a standalone helper so scheduler tests don't need to mock
    APScheduler internals to exercise it."""
    today_target = datetime.combine(
        now.date(), time(schedule.send_hour_utc, schedule.send_minute_utc), tzinfo=UTC
    )
    return now >= today_target


def _run_daily_report() -> None:
    try:
        asyncio.run(_run_daily_report_async())
    except Exception:
        logger.exception("scheduled daily report job crashed")  # never let this kill the scheduler


async def _run_daily_report_async() -> None:
    session_factory = create_session_factory()
    settings = get_settings()
    now = datetime.now(UTC)
    # Operational Day = Asia/Dhaka calendar day (PRD Glossary) — same
    # UTC->Dhaka conversion api/dashboard/routes.py and
    # scripts/seed_demo_data.py already use.
    today = now.astimezone(ZoneInfo("Asia/Dhaka")).date()

    async with session_factory() as session:
        schedule = await SqlAlchemyReportScheduleRepository(session).get()
        if not _should_run_daily_report(now, schedule):
            return

        deliveries = SqlAlchemyNotificationDeliveryRepository(session)
        # The interval job (Story 4.4) re-enters this function on every poll
        # tick for the rest of the day once _should_run_daily_report goes
        # true — without this check, each tick would call
        # ScheduledReportService.run_daily_report() again, which creates and
        # commits a new Notification row *before* reaching AD-2's partial
        # unique index (that index lives on notification_deliveries, not
        # notifications), leaving a zero-delivery orphan Notification behind
        # every tick. Only Scheduled deliveries ever set operational_day
        # (Manual always passes None), so this is a cheap, correct "already
        # dispatched today" check (code review).
        if await deliveries.exists_for_operational_day(today):
            return

        users = SqlAlchemyUserRepository(session)
        teams = SqlAlchemyTeamRepository(session)
        notifications = SqlAlchemyNotificationRepository(session)
        templates = SqlAlchemyMessageTemplateRepository(session)

        resolution = RecipientResolutionService(
            users,
            SqlAlchemyRecipientListRepository(session),
            SqlAlchemyOptInConsentRepository(session),
            teams,
        )
        content = DailyReportContentService(
            dashboard_metrics=DashboardMetricsService(
                sales_data=SqlAlchemySalesDataRepository(session),
                teams=teams,
                import_runs=SqlAlchemyImportRunRepository(session),
                stale_after=timedelta(hours=settings.dashboard_stale_after_hours),
            ),
            brand_performance=BrandPerformanceService(
                brand_performance=SqlAlchemyBrandPerformanceRepository(session),
                top_n=settings.brand_top_n,
                low_performing_n=settings.brand_low_performing_n,
                focus_n=settings.brand_focus_n,
            ),
            doctor_visit_list=DoctorVisitListService(SqlAlchemyDoctorRepository(session)),
            teams=teams,
            top_doctors_n=settings.report_top_doctors_n,
        )
        service = ScheduledReportService(
            notifications=notifications,
            deliveries=deliveries,
            templates=templates,
            users=users,
            resolution=resolution,
            content=content,
            whatsapp=TwilioWhatsAppSender(),
            max_retry_attempts=settings.notification_max_retry_attempts,
        )

        # ScheduledReportService.run_daily_report already catches AD-2's
        # partial-unique-index duplicate rejection internally (a same-day
        # duplicate that slipped past the advisory lock, e.g. a scheduler
        # restart between the lock's commit and a cron misfire re-trigger)
        # and returns a clean SKIPPED outcome — no IntegrityError escapes
        # to this composition-root layer.
        await service.run_daily_report(today, now)
        await session.commit()


def _run_retry_failed_deliveries() -> None:
    try:
        asyncio.run(_run_retry_failed_deliveries_async())
    except Exception:
        logger.exception("retry failed deliveries job crashed")  # never let this kill the scheduler


async def _run_retry_failed_deliveries_async() -> None:
    session_factory = create_session_factory()
    settings = get_settings()
    now = datetime.now(UTC)

    async with session_factory() as session:
        deliveries = SqlAlchemyNotificationDeliveryRepository(session)
        notifications = SqlAlchemyNotificationRepository(session)
        templates = SqlAlchemyMessageTemplateRepository(session)
        users = SqlAlchemyUserRepository(session)
        whatsapp = TwilioWhatsAppSender()

        rows = await deliveries.list_retry_eligible(now)
        for row in rows:
            try:
                notification = await notifications.get_by_id(row.notification_id)
                template = (
                    await templates.get_by_id(notification.template_id)
                    if notification is not None
                    else None
                )
                recipient = await users.get_by_id(row.recipient_user_id)

                # A missing Notification/MessageTemplate/recipient
                # (soft-delete makes this rare) must still consume a retry
                # attempt rather than being silently skipped —
                # dispatch_deliveries' own "recipient not found" branch
                # already implements exactly that outcome (claim, then fail
                # via _status_after_failed_attempt), so an empty
                # recipients_by_id reuses it here rather than a second copy
                # of the claim/send/record logic (Task 4 Step 8's
                # extraction is exactly what this reuses). The specific
                # missing record is logged here since dispatch_deliveries'
                # shared failure_reason column always records the same
                # generic "recipient no longer exists" string regardless of
                # which record was actually missing.
                if notification is None or template is None or recipient is None:
                    logger.warning(
                        "retry delivery has a missing related record",
                        extra={
                            "delivery_id": str(row.id),
                            "notification_found": notification is not None,
                            "template_found": template is not None,
                            "recipient_found": recipient is not None,
                        },
                    )
                recipients_by_id = (
                    {recipient.id: recipient}
                    if template is not None and recipient is not None
                    else {}
                )
                template_content_sid = template.twilio_content_sid if template is not None else ""

                await dispatch_deliveries(
                    deliveries=deliveries,
                    whatsapp=whatsapp,
                    delivery_rows=[row],
                    content_variables_by_recipient={row.recipient_user_id: row.content_variables},
                    template_content_sid=template_content_sid,
                    recipients_by_id=recipients_by_id,
                    max_retry_attempts=settings.notification_max_retry_attempts,
                )
            except Exception:
                # Isolate one row's failure (e.g. a transient DB error on
                # one of the lookups above) from the rest of the batch —
                # committing per row below means an exception here can
                # only roll back this row's own not-yet-committed work,
                # never a prior row's already-recorded, already-sent
                # outcome.
                logger.exception(
                    "retry delivery dispatch failed, will be retried next poll",
                    extra={"delivery_id": str(row.id)},
                )
                await session.rollback()
                continue

            await session.commit()

        # Also reached (as a harmless no-op commit) when rows is empty —
        # matches every other job's contract of always committing once per
        # run, even a run with nothing to do.
        await session.commit()


def _register_jobs(scheduler: BlockingScheduler) -> None:
    scheduler.add_job(_heartbeat, "interval", seconds=30, id="heartbeat")
    # [ASSUMPTION — CONFIRM] Trigger time: neither the PRD nor the epics
    # specify an exact nightly time — only "every night". 19:30 UTC =
    # 01:30 Asia/Dhaka (UTC+6) is this story's own placeholder, chosen to
    # land after the business day closes locally and comfortably ahead of
    # an early-morning Dashboard check. Must be confirmed with a business
    # stakeholder before this is treated as final — configurable (like
    # source_system_import_dir) precisely because it's still provisional.
    settings = get_settings()
    scheduler.add_job(
        _run_nightly_import,
        "cron",
        hour=settings.nightly_import_cron_hour,
        minute=settings.nightly_import_cron_minute,
        id="nightly_import",
    )
    # "interval", not "cron": the ReportSchedule row (AD-11, Story 4.4) is
    # DB-backed and Administrator-editable via Settings, so a redeploy must
    # never be required to change the send time — a cron trigger's
    # hour/minute is fixed at process-start, which would defeat that.
    # Mirrors retry_failed_deliveries's own "poll continuously, read current
    # DB state inside the job" shape. _should_run_daily_report reads the
    # fresh schedule on every tick and decides whether to actually dispatch.
    scheduler.add_job(
        _run_daily_report,
        "interval",
        seconds=settings.report_schedule_poll_interval_seconds,
        id="daily_report",
    )
    # "interval", not "cron": this polls continuously for retry-eligible
    # deliveries rather than firing at a fixed time of day. APScheduler's
    # default max_instances=1 per job already prevents overlapping runs if
    # one poll cycle runs long — no advisory lock key needed, since
    # claim_for_dispatch's existing atomic conditional UPDATE is what
    # actually guards against double-dispatch (Story 4.3).
    scheduler.add_job(
        _run_retry_failed_deliveries,
        "interval",
        seconds=settings.notification_retry_poll_interval_seconds,
        id="retry_failed_deliveries",
    )


def main() -> None:
    _configure_logging()
    scheduler = BlockingScheduler(timezone="UTC")
    _register_jobs(scheduler)

    def _handle_sigterm(signum: int, frame: object) -> None:
        # `docker stop` / a redeploy sends SIGTERM to PID 1. Python does not
        # turn that into KeyboardInterrupt/SystemExit by default, so without
        # this handler the process dies immediately mid-job — exactly what
        # running the scheduler as its own container exists to prevent
        # (AD-5). Shut down gracefully instead.
        logger.info("SIGTERM received, shutting down scheduler gracefully")
        scheduler.shutdown(wait=True)

    signal.signal(signal.SIGTERM, _handle_sigterm)

    logger.info("scheduler starting")
    _heartbeat()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
