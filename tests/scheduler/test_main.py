import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from apscheduler.schedulers.blocking import BlockingScheduler

from domain.models import DeliveryStatus, NotificationDelivery, NotificationType
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
