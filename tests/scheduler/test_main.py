import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from apscheduler.schedulers.blocking import BlockingScheduler

from domain.models import DeliveryStatus, NotificationDelivery, NotificationType, ReportSchedule
from scheduler import main as scheduler_main


def _retry_eligible_delivery(**overrides):
    defaults = dict(
        id=uuid.uuid4(),
        notification_id=uuid.uuid4(),
        notification_type=NotificationType.MANUAL,
        recipient_user_id=uuid.uuid4(),
        operational_day=None,
        status=DeliveryStatus.FAILED_RETRYABLE,
        attempt_count=1,
        provider_message_sid="SMold",
        failure_reason="transient error",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        content_variables={"1": "value"},
    )
    defaults.update(overrides)
    return NotificationDelivery(**defaults)


def test_register_jobs_registers_heartbeat_and_nightly_import():
    scheduler = BlockingScheduler(timezone="UTC")

    scheduler_main._register_jobs(scheduler)

    assert scheduler.get_job("heartbeat") is not None
    nightly_import = scheduler.get_job("nightly_import")
    assert nightly_import is not None
    settings = scheduler_main.get_settings()
    trigger_fields = {field.name: str(field) for field in nightly_import.trigger.fields}
    assert trigger_fields["hour"] == str(settings.nightly_import_cron_hour)
    assert trigger_fields["minute"] == str(settings.nightly_import_cron_minute)


def test_register_jobs_registers_daily_report_as_an_interval_job_not_cron():
    scheduler = BlockingScheduler(timezone="UTC")

    scheduler_main._register_jobs(scheduler)

    daily_report = scheduler.get_job("daily_report")
    assert daily_report is not None
    settings = scheduler_main.get_settings()
    expected_seconds = settings.report_schedule_poll_interval_seconds
    assert daily_report.trigger.interval.total_seconds() == expected_seconds


@pytest.mark.parametrize(
    "now,schedule_hour,schedule_minute,expected",
    [
        # now before today's target -> False.
        (datetime(2026, 7, 23, 0, 59, tzinfo=UTC), 1, 0, False),
        # now exactly at today's target (same day) -> True.
        (datetime(2026, 7, 23, 1, 0, tzinfo=UTC), 1, 0, True),
        # now after today's target (same day) -> True.
        (datetime(2026, 7, 23, 1, 1, tzinfo=UTC), 1, 0, True),
        # A schedule crossing UTC midnight is still evaluated purely in UTC
        # terms for "today" — no Asia/Dhaka date-boundary confusion.
        (datetime(2026, 7, 23, 23, 30, tzinfo=UTC), 23, 45, False),
        (datetime(2026, 7, 23, 23, 45, tzinfo=UTC), 23, 45, True),
    ],
)
def test_should_run_daily_report(now, schedule_hour, schedule_minute, expected):
    schedule = ReportSchedule(
        id=uuid.uuid4(),
        send_hour_utc=schedule_hour,
        send_minute_utc=schedule_minute,
        updated_at=now,
        updated_by_user_id=None,
    )

    assert scheduler_main._should_run_daily_report(now, schedule) == expected


async def test_run_daily_report_async_skips_dispatch_when_todays_target_has_not_arrived(
    monkeypatch,
):
    # An hour from now, same UTC calendar day guaranteed by capping to 23:59
    # — always in the future relative to "now" regardless of when the test
    # itself runs.
    now = datetime.now(UTC)
    future_hour = min(now.hour + 1, 23)
    future_schedule = ReportSchedule(
        id=uuid.uuid4(),
        send_hour_utc=future_hour,
        send_minute_utc=59,
        updated_at=now,
        updated_by_user_id=None,
    )

    class _FakeReportScheduleRepository:
        async def get(self):
            return future_schedule

    class _FakeSession:
        async def __aenter__(self) -> "_FakeSession":
            return self

        async def __aexit__(self, *exc_info) -> None:
            return None

    monkeypatch.setattr(scheduler_main, "create_session_factory", lambda: (lambda: _FakeSession()))
    monkeypatch.setattr(
        scheduler_main,
        "SqlAlchemyReportScheduleRepository",
        lambda session: _FakeReportScheduleRepository(),
    )

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("ScheduledReportService must not be constructed when skipping")

    monkeypatch.setattr(scheduler_main, "ScheduledReportService", _fail_if_called)

    await scheduler_main._run_daily_report_async()  # must not raise


async def test_run_daily_report_async_skips_dispatch_when_already_sent_today(monkeypatch):
    # Regression test (code review): the interval job re-enters this
    # function on every poll tick for the rest of the day once today's
    # target time has passed — without this guard, each tick would call
    # ScheduledReportService again, creating a new orphan Notification row
    # before AD-2's partial unique index (on notification_deliveries, not
    # notifications) ever catches the duplicate.
    now = datetime.now(UTC)
    past_schedule = ReportSchedule(
        id=uuid.uuid4(),
        send_hour_utc=0,
        send_minute_utc=0,
        updated_at=now,
        updated_by_user_id=None,
    )

    class _FakeReportScheduleRepository:
        async def get(self):
            return past_schedule

    class _FakeDeliveries:
        async def exists_for_operational_day(self, operational_day):
            return True

    class _FakeSession:
        async def __aenter__(self) -> "_FakeSession":
            return self

        async def __aexit__(self, *exc_info) -> None:
            return None

    monkeypatch.setattr(scheduler_main, "create_session_factory", lambda: (lambda: _FakeSession()))
    monkeypatch.setattr(
        scheduler_main,
        "SqlAlchemyReportScheduleRepository",
        lambda session: _FakeReportScheduleRepository(),
    )
    monkeypatch.setattr(
        scheduler_main,
        "SqlAlchemyNotificationDeliveryRepository",
        lambda session: _FakeDeliveries(),
    )

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("ScheduledReportService must not be constructed when skipping")

    monkeypatch.setattr(scheduler_main, "ScheduledReportService", _fail_if_called)

    await scheduler_main._run_daily_report_async()  # must not raise


def test_register_jobs_registers_retry_failed_deliveries_with_the_configured_interval():
    scheduler = BlockingScheduler(timezone="UTC")

    scheduler_main._register_jobs(scheduler)

    retry_job = scheduler.get_job("retry_failed_deliveries")
    assert retry_job is not None
    settings = scheduler_main.get_settings()
    expected_seconds = settings.notification_retry_poll_interval_seconds
    assert retry_job.trigger.interval.total_seconds() == expected_seconds


def test_run_retry_failed_deliveries_swallows_exceptions_instead_of_crashing_the_scheduler(
    monkeypatch,
):
    async def _raising_async() -> None:
        raise RuntimeError("simulated retry job crash")

    monkeypatch.setattr(scheduler_main, "_run_retry_failed_deliveries_async", _raising_async)

    scheduler_main._run_retry_failed_deliveries()  # must not raise


async def test_run_retry_failed_deliveries_async_wires_the_service_and_commits(monkeypatch):
    calls: list[str] = []

    class _FakeDeliveries:
        async def list_retry_eligible(self, now):
            calls.append("list_retry_eligible")
            return []

    class _FakeSession:
        async def commit(self) -> None:
            calls.append("commit")

        async def __aenter__(self) -> "_FakeSession":
            return self

        async def __aexit__(self, *exc_info) -> None:
            return None

    def _fake_session_factory():
        return _FakeSession()

    monkeypatch.setattr(scheduler_main, "create_session_factory", lambda: _fake_session_factory)
    monkeypatch.setattr(
        scheduler_main,
        "SqlAlchemyNotificationDeliveryRepository",
        lambda session: _FakeDeliveries(),
    )

    await scheduler_main._run_retry_failed_deliveries_async()

    assert calls == ["list_retry_eligible", "commit"]


class _FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.rollback_count = 0

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *exc_info) -> None:
        return None


def _patch_retry_session(monkeypatch, deliveries) -> _FakeSession:
    session = _FakeSession()
    monkeypatch.setattr(scheduler_main, "create_session_factory", lambda: (lambda: session))
    monkeypatch.setattr(
        scheduler_main, "SqlAlchemyNotificationDeliveryRepository", lambda session: deliveries
    )
    monkeypatch.setattr(scheduler_main, "TwilioWhatsAppSender", lambda: object())
    return session


def _patch_lookup_repos(monkeypatch, notifications, templates, users) -> None:
    monkeypatch.setattr(
        scheduler_main, "SqlAlchemyNotificationRepository", lambda session: notifications
    )
    monkeypatch.setattr(
        scheduler_main, "SqlAlchemyMessageTemplateRepository", lambda session: templates
    )
    monkeypatch.setattr(scheduler_main, "SqlAlchemyUserRepository", lambda session: users)


async def test_run_retry_failed_deliveries_async_resolves_lookup_chain_and_dispatches(monkeypatch):
    row = _retry_eligible_delivery()
    notification = SimpleNamespace()
    template = SimpleNamespace()
    recipient = SimpleNamespace()
    dispatch_calls: list[dict] = []

    class _FakeDeliveries:
        async def list_retry_eligible(self, now):
            return [row]

    class _FakeNotifications:
        async def get_by_id(self, notification_id):
            return notification

    class _FakeTemplates:
        async def get_by_id(self, template_id):
            return template

    class _FakeUsers:
        async def get_by_id(self, user_id):
            return recipient

    async def _fake_dispatch_deliveries(**kwargs):
        dispatch_calls.append(kwargs)
        return []

    notification.template_id = uuid.uuid4()
    template.twilio_content_sid = "HXsomecontentsid"
    recipient.id = row.recipient_user_id

    session = _patch_retry_session(monkeypatch, _FakeDeliveries())
    _patch_lookup_repos(monkeypatch, _FakeNotifications(), _FakeTemplates(), _FakeUsers())
    monkeypatch.setattr(scheduler_main, "dispatch_deliveries", _fake_dispatch_deliveries)

    await scheduler_main._run_retry_failed_deliveries_async()

    assert len(dispatch_calls) == 1
    call = dispatch_calls[0]
    assert call["recipients_by_id"] == {recipient.id: recipient}
    assert call["template_content_sid"] == "HXsomecontentsid"
    assert call["delivery_rows"] == [row]
    assert session.commit_count >= 1


async def test_run_retry_failed_deliveries_async_missing_template_dispatches_with_empty_recipients(
    monkeypatch,
):
    row = _retry_eligible_delivery()
    notification = SimpleNamespace()
    dispatch_calls: list[dict] = []

    class _FakeDeliveries:
        async def list_retry_eligible(self, now):
            return [row]

    class _FakeNotifications:
        async def get_by_id(self, notification_id):
            return notification

    class _FakeTemplates:
        async def get_by_id(self, template_id):
            return None  # MessageTemplate was deleted

    class _FakeUsers:
        async def get_by_id(self, user_id):
            return object()

    async def _fake_dispatch_deliveries(**kwargs):
        dispatch_calls.append(kwargs)
        return []

    notification.template_id = uuid.uuid4()

    _patch_retry_session(monkeypatch, _FakeDeliveries())
    _patch_lookup_repos(monkeypatch, _FakeNotifications(), _FakeTemplates(), _FakeUsers())
    monkeypatch.setattr(scheduler_main, "dispatch_deliveries", _fake_dispatch_deliveries)

    await scheduler_main._run_retry_failed_deliveries_async()

    assert len(dispatch_calls) == 1
    assert dispatch_calls[0]["recipients_by_id"] == {}
    assert dispatch_calls[0]["template_content_sid"] == ""


async def test_run_retry_failed_deliveries_async_isolates_a_failing_row_from_the_rest_of_the_batch(
    monkeypatch,
):
    failing_row = _retry_eligible_delivery()
    ok_row = _retry_eligible_delivery()
    notification = SimpleNamespace()
    template = SimpleNamespace()
    recipient = SimpleNamespace()
    dispatch_calls: list[dict] = []

    class _FakeDeliveries:
        async def list_retry_eligible(self, now):
            return [failing_row, ok_row]

    class _FakeNotifications:
        async def get_by_id(self, notification_id):
            if notification_id == failing_row.notification_id:
                raise RuntimeError("simulated transient DB error")
            return notification

    class _FakeTemplates:
        async def get_by_id(self, template_id):
            return template

    class _FakeUsers:
        async def get_by_id(self, user_id):
            return recipient

    async def _fake_dispatch_deliveries(**kwargs):
        dispatch_calls.append(kwargs)
        return []

    notification.template_id = uuid.uuid4()
    template.twilio_content_sid = "HXsomecontentsid"
    recipient.id = ok_row.recipient_user_id

    session = _patch_retry_session(monkeypatch, _FakeDeliveries())
    _patch_lookup_repos(monkeypatch, _FakeNotifications(), _FakeTemplates(), _FakeUsers())
    monkeypatch.setattr(scheduler_main, "dispatch_deliveries", _fake_dispatch_deliveries)

    await scheduler_main._run_retry_failed_deliveries_async()  # must not raise

    assert len(dispatch_calls) == 1
    assert dispatch_calls[0]["delivery_rows"] == [ok_row]
    assert session.rollback_count == 1
    assert session.commit_count >= 1


def test_run_nightly_import_swallows_exceptions_instead_of_crashing_the_scheduler(monkeypatch):
    async def _raising_async() -> None:
        raise RuntimeError("simulated pipeline crash")

    monkeypatch.setattr(scheduler_main, "_run_nightly_import_async", _raising_async)

    scheduler_main._run_nightly_import()  # must not raise


async def test_run_nightly_import_async_wires_the_service_and_commits(monkeypatch):
    calls: list[str] = []

    class _FakeService:
        def __init__(self, **kwargs) -> None:
            calls.append("constructed")

        async def run(self):
            calls.append("run")

    class _FakeSession:
        async def commit(self) -> None:
            calls.append("commit")

        async def __aenter__(self) -> "_FakeSession":
            return self

        async def __aexit__(self, *exc_info) -> None:
            return None

    def _fake_session_factory():
        return _FakeSession()

    monkeypatch.setattr(scheduler_main, "create_session_factory", lambda: _fake_session_factory)
    monkeypatch.setattr(scheduler_main, "SourceSystemImportService", _FakeService)

    await scheduler_main._run_nightly_import_async()

    assert calls == ["constructed", "run", "commit"]
