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
from datetime import UTC, datetime, timedelta
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
from adapters.persistence.staging import SqlAlchemyStagingRepository
from adapters.persistence.teams import SqlAlchemyTeamRepository
from adapters.persistence.users import SqlAlchemyUserRepository
from adapters.source_system.csv_importer import CsvFileSourceSystemImporter
from adapters.whatsapp_twilio.sender import TwilioWhatsAppSender
from config import get_settings
from domain.daily_report import DailyReportContentService
from domain.ingestion import SourceSystemImportService
from domain.metrics import BrandPerformanceService, DashboardMetricsService, DoctorVisitListService
from domain.notifications import RecipientResolutionService
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
        users = SqlAlchemyUserRepository(session)
        teams = SqlAlchemyTeamRepository(session)
        notifications = SqlAlchemyNotificationRepository(session)
        deliveries = SqlAlchemyNotificationDeliveryRepository(session)
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
        )

        # ScheduledReportService.run_daily_report already catches AD-2's
        # partial-unique-index duplicate rejection internally (a same-day
        # duplicate that slipped past the advisory lock, e.g. a scheduler
        # restart between the lock's commit and a cron misfire re-trigger)
        # and returns a clean SKIPPED outcome — no IntegrityError escapes
        # to this composition-root layer.
        await service.run_daily_report(today, now)
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
    # [ASSUMPTION — CONFIRM] 01:00 UTC = 07:00 Asia/Dhaka default — the
    # PRD's own stated placeholder (see config.py's report_send_cron_hour
    # docstring), still pending business confirmation.
    scheduler.add_job(
        _run_daily_report,
        "cron",
        hour=settings.report_send_cron_hour,
        minute=settings.report_send_cron_minute,
        id="daily_report",
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
