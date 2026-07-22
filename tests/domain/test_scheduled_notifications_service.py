import uuid
from datetime import UTC, date, datetime

from domain.daily_report import CompanyWideReportContent
from domain.models import (
    DeliveryStatus,
    MessageTemplate,
    NotificationType,
    Role,
    Team,
    TeamStatus,
    User,
    UserStatus,
)
from domain.notifications import RecipientResolutionService
from domain.scheduled_notifications import (
    DAILY_REPORT_TEMPLATE_NAME,
    ScheduledReportOutcome,
    ScheduledReportService,
)
from ports.whatsapp import SendResult, WhatsAppSendError

_TODAY = date(2026, 7, 22)
_NOW = datetime(2026, 7, 22, 1, 0, tzinfo=UTC)


def _make_user(
    mobile: str = "+8801700000000",
    team_id: uuid.UUID | None = None,
    status: UserStatus = UserStatus.ACTIVE,
) -> User:
    return User(
        id=uuid.uuid4(),
        username=None,
        hashed_password=None,
        role=Role.SALES_USER,
        status=status,
        version=1,
        created_at=datetime.now(UTC),
        name="Rahim",
        mobile=mobile,
        team_id=team_id,
    )


def _make_template(slots: list[str] | None = None) -> MessageTemplate:
    return MessageTemplate(
        id=uuid.uuid4(),
        name=DAILY_REPORT_TEMPLATE_NAME,
        twilio_content_sid="HXdaily123",
        variable_slots=slots if slots is not None else ["ytd_sales"],
        body_preview_template="{ytd_sales}",
        created_at=datetime.now(UTC),
    )


class FakeUserRepository:
    def __init__(self, users: list[User] | None = None) -> None:
        self._by_id = {u.id: u for u in (users or [])}

    async def list_all(self) -> list[User]:
        return list(self._by_id.values())

    async def get_many_by_ids(self, user_ids: list[uuid.UUID]) -> list[User]:
        return [self._by_id[uid] for uid in user_ids if uid in self._by_id]

    async def list_by_team_id(self, team_id: uuid.UUID) -> list[User]:
        return [u for u in self._by_id.values() if u.team_id == team_id]


class FakeRecipientListRepository:
    async def get_by_id(self, recipient_list_id: uuid.UUID):
        return None


class FakeTeamRepository:
    async def get_by_id(self, team_id: uuid.UUID) -> Team:
        return Team(id=team_id, name="Team", status=TeamStatus.ACTIVE, version=1)


class FakeOptInConsentRepository:
    def __init__(self, opted_in_user_ids: set[uuid.UUID] | None = None) -> None:
        self._opted_in = opted_in_user_ids or set()

    async def get_active_by_user_ids(self, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, object]:
        return {uid: object() for uid in user_ids if uid in self._opted_in}


class FakeMessageTemplateRepository:
    def __init__(self, templates: list[MessageTemplate] | None = None) -> None:
        self._by_name = {t.name: t for t in (templates or [])}

    async def get_by_name(self, name: str) -> MessageTemplate | None:
        return self._by_name.get(name)


class FakeNotificationRepository:
    def __init__(self, lock_available: bool = True) -> None:
        self._lock_available = lock_available
        self.added: list[tuple] = []

    async def try_acquire_daily_report_lock(self) -> bool:
        return self._lock_available

    async def add(self, notification, targets) -> None:
        self.added.append((notification, targets))


class FakeNotificationDeliveryRepository:
    def __init__(self, fail_bulk_create_with: Exception | None = None) -> None:
        self._fail_bulk_create_with = fail_bulk_create_with
        self.bulk_create_calls = 0
        self.bulk_created: list = []
        self._by_id: dict = {}

    async def bulk_create(self, rows: list) -> None:
        self.bulk_create_calls += 1
        if self._fail_bulk_create_with is not None and self.bulk_create_calls >= 2:
            raise self._fail_bulk_create_with
        self.bulk_created.extend(rows)
        for row in rows:
            self._by_id[row.id] = row

    async def claim_for_dispatch(self, delivery_id: uuid.UUID) -> bool:
        row = self._by_id.get(delivery_id)
        if row is None or row.status not in (
            DeliveryStatus.QUEUED,
            DeliveryStatus.FAILED_RETRYABLE,
        ):
            return False
        row.status = DeliveryStatus.SENDING
        return True

    async def update_after_send(self, delivery_id, status, provider_message_sid, failure_reason):
        row = self._by_id.get(delivery_id)
        if row is not None:
            row.status = status
            row.provider_message_sid = provider_message_sid
            row.failure_reason = failure_reason

    async def most_recent_status_summary(self):
        return None


class FakeWhatsAppSender:
    def __init__(self) -> None:
        self.sent: list[tuple] = []

    async def send_template_message(self, to_number, content_sid, content_variables) -> SendResult:
        self.sent.append((to_number, content_sid, content_variables))
        return SendResult(provider_message_sid=f"SM-{to_number}")


class FakeDailyReportContentService:
    """Fake, not the real DailyReportContentService — its own behavior is
    covered by tests/domain/test_daily_report_content.py; here we only
    need to assert ScheduledReportService's *calling* discipline (once per
    run for company-wide content, once per distinct territory for the
    doctor section)."""

    def __init__(
        self,
        territory_by_recipient: dict[uuid.UUID, str] | None = None,
        doctor_sections: dict[str, str] | None = None,
    ) -> None:
        self._territory_by_recipient = territory_by_recipient or {}
        self._doctor_sections = doctor_sections or {}
        self.build_doctor_section_calls: list[str] = []

    async def build_company_wide_content(self, today, now) -> CompanyWideReportContent:
        return CompanyWideReportContent(
            ytd_sales="100.0 Cr BDT",
            mtd_sales="12.0 Cr BDT",
            achievement_pct="40%",
            growth_pct="10%",
            team_performance="Team A : 45%",
            top_brand="ABC Pharma",
            focus_brand="XYZ Pharma",
        )

    async def resolve_territories(self, recipients) -> dict[uuid.UUID, str]:
        return {r.id: self._territory_by_recipient.get(r.id, "Unassigned") for r in recipients}

    async def build_doctor_section(self, territory: str) -> str:
        self.build_doctor_section_calls.append(territory)
        return self._doctor_sections.get(territory, "Dr. Rahman")


def _resolution(users: list[User], opted_in_user_ids: set[uuid.UUID]) -> RecipientResolutionService:
    return RecipientResolutionService(
        FakeUserRepository(users),
        FakeRecipientListRepository(),
        FakeOptInConsentRepository(opted_in_user_ids),
        FakeTeamRepository(),
    )


def _service(
    users: list[User],
    opted_in_user_ids: set[uuid.UUID],
    notifications: FakeNotificationRepository | None = None,
    deliveries: FakeNotificationDeliveryRepository | None = None,
    templates: FakeMessageTemplateRepository | None = None,
    content: FakeDailyReportContentService | None = None,
    whatsapp: FakeWhatsAppSender | None = None,
    max_retry_attempts: int = 3,
) -> tuple[
    ScheduledReportService,
    FakeNotificationRepository,
    FakeNotificationDeliveryRepository,
    FakeDailyReportContentService,
]:
    notifications = notifications or FakeNotificationRepository()
    deliveries = deliveries or FakeNotificationDeliveryRepository()
    templates = templates or FakeMessageTemplateRepository([_make_template()])
    content = content or FakeDailyReportContentService()
    whatsapp = whatsapp or FakeWhatsAppSender()
    service = ScheduledReportService(
        notifications=notifications,
        deliveries=deliveries,
        templates=templates,
        users=FakeUserRepository(users),
        resolution=_resolution(users, opted_in_user_ids),
        content=content,
        whatsapp=whatsapp,
        max_retry_attempts=max_retry_attempts,
    )
    return service, notifications, deliveries, content


async def test_run_daily_report_happy_path_creates_one_delivery_per_recipient():
    u1 = _make_user(mobile="+8801700001001")
    u2 = _make_user(mobile="+8801700001002")
    service, notifications, deliveries, _ = _service([u1, u2], {u1.id, u2.id})

    result = await service.run_daily_report(_TODAY, _NOW)

    assert result.outcome == ScheduledReportOutcome.SUCCEEDED
    assert result.recipient_count == 2

    assert len(notifications.added) == 1
    notification, targets = notifications.added[0]
    assert notification.notification_type == NotificationType.SCHEDULED
    assert notification.created_by_user_id is None
    assert targets == []

    assert len(deliveries.bulk_created) == 2
    for row in deliveries.bulk_created:
        assert row.notification_type == NotificationType.SCHEDULED
        assert row.operational_day == _TODAY
    assert {row.recipient_user_id for row in deliveries.bulk_created} == {u1.id, u2.id}


async def test_run_daily_report_logs_dispatch_outcome_counts_including_failures(caplog):
    # Regression test (code review): a run's actual dispatch outcome
    # (including partial/total failures, e.g. a Twilio outage) must be
    # logged somewhere — ScheduledReportResult's own SUCCEEDED/SKIPPED
    # outcome doesn't capture per-recipient dispatch failures, and nothing
    # else logs a run's completion.
    u1 = _make_user(mobile="+8801700001013")
    u2 = _make_user(mobile="+8801700001014")

    class FlakyWhatsAppSender(FakeWhatsAppSender):
        async def send_template_message(self, to_number, content_sid, content_variables):
            if to_number == u2.mobile:
                raise WhatsAppSendError("simulated Twilio outage")
            return await super().send_template_message(to_number, content_sid, content_variables)

    service, *_ = _service([u1, u2], {u1.id, u2.id}, whatsapp=FlakyWhatsAppSender())

    with caplog.at_level("INFO"):
        result = await service.run_daily_report(_TODAY, _NOW)

    assert result.outcome == ScheduledReportOutcome.SUCCEEDED
    matching = [
        r for r in caplog.records if r.message == "scheduled daily report dispatch complete"
    ]
    assert len(matching) == 1
    assert matching[0].failed_count == 1
    assert matching[0].recipient_count == 2


async def test_run_daily_report_calls_build_doctor_section_once_per_distinct_territory():
    team_id = uuid.uuid4()
    u1 = _make_user(mobile="+8801700001003", team_id=team_id)
    u2 = _make_user(mobile="+8801700001004", team_id=team_id)
    content = FakeDailyReportContentService(
        territory_by_recipient={u1.id: "North Region", u2.id: "North Region"}
    )
    service, _, _, content = _service([u1, u2], {u1.id, u2.id}, content=content)

    await service.run_daily_report(_TODAY, _NOW)

    assert content.build_doctor_section_calls == ["North Region"]


async def test_run_daily_report_with_zero_eligible_recipients_completes_cleanly():
    inactive = _make_user(mobile="+8801700001005", status=UserStatus.INACTIVE)
    service, notifications, deliveries, _ = _service([inactive], set())

    result = await service.run_daily_report(_TODAY, _NOW)

    assert result.outcome == ScheduledReportOutcome.SKIPPED
    assert notifications.added == []
    assert deliveries.bulk_created == []


async def test_run_daily_report_returns_skipped_when_the_advisory_lock_is_already_held():
    u1 = _make_user(mobile="+8801700001006")
    notifications = FakeNotificationRepository(lock_available=False)
    service, _, deliveries, _ = _service([u1], {u1.id}, notifications=notifications)

    result = await service.run_daily_report(_TODAY, _NOW)

    assert result.outcome == ScheduledReportOutcome.SKIPPED
    assert deliveries.bulk_created == []


async def test_run_daily_report_returns_skipped_when_the_template_is_not_provisioned():
    u1 = _make_user(mobile="+8801700001007")
    service, notifications, deliveries, _ = _service(
        [u1], {u1.id}, templates=FakeMessageTemplateRepository([])
    )

    result = await service.run_daily_report(_TODAY, _NOW)

    assert result.outcome == ScheduledReportOutcome.SKIPPED
    assert notifications.added == []
    assert deliveries.bulk_created == []


async def test_run_daily_report_returns_skipped_when_the_template_has_an_unrecognized_slot():
    # Regression test (code review): Story 4.5's generic template editor
    # lets an Administrator set variable_slots to anything non-blank/
    # unique — it has no awareness of this template's fixed 8-field
    # contract. An unrecognized slot name must be caught here (and
    # skipped cleanly) rather than raising an uncaught KeyError later
    # while building content_variables_by_recipient.
    u1 = _make_user(mobile="+8801700001010")
    bad_template = _make_template(slots=["ytd_sales", "not_a_real_slot"])
    service, notifications, deliveries, _ = _service(
        [u1], {u1.id}, templates=FakeMessageTemplateRepository([bad_template])
    )

    result = await service.run_daily_report(_TODAY, _NOW)

    assert result.outcome == ScheduledReportOutcome.SKIPPED
    assert notifications.added == []
    assert deliveries.bulk_created == []


async def test_run_daily_report_skips_a_recipient_deleted_between_resolve_and_get_many_by_ids():
    # Regression test (code review): resolved.recipient_user_ids can
    # include a recipient that self._users.get_many_by_ids() no longer
    # returns (deleted mid-run, possible under Postgres's default READ
    # COMMITTED isolation) — this must not raise KeyError and abort the
    # whole run; that recipient's delivery row is simply skipped here
    # (dispatch_deliveries' own recipients_by_id.get(...) check already
    # fails that row gracefully rather than sending to it).
    u1 = _make_user(mobile="+8801700001011")
    u2 = _make_user(mobile="+8801700001012")

    class VanishingUserRepository(FakeUserRepository):
        async def get_many_by_ids(self, user_ids: list[uuid.UUID]) -> list[User]:
            return [u for u in await super().get_many_by_ids(user_ids) if u.id != u2.id]

    notifications = FakeNotificationRepository()
    deliveries = FakeNotificationDeliveryRepository()
    templates = FakeMessageTemplateRepository([_make_template()])
    content = FakeDailyReportContentService()
    whatsapp = FakeWhatsAppSender()
    service = ScheduledReportService(
        notifications=notifications,
        deliveries=deliveries,
        templates=templates,
        users=VanishingUserRepository([u1, u2]),
        resolution=_resolution([u1, u2], {u1.id, u2.id}),
        content=content,
        whatsapp=whatsapp,
        max_retry_attempts=3,
    )

    result = await service.run_daily_report(_TODAY, _NOW)

    assert result.outcome == ScheduledReportOutcome.SUCCEEDED
    assert len(whatsapp.sent) == 1  # only u1 dispatched; u2 silently skipped, not a crash


async def test_run_daily_report_catches_a_duplicate_operational_day_bulk_create_failure():
    # Simulates AD-2's partial unique index rejecting a same-day duplicate
    # that slipped past the advisory lock — a fake raising the DB
    # unique-constraint IntegrityError *shape* on the second bulk_create
    # call (any Exception works here; the domain layer can't name
    # sqlalchemy.exc.IntegrityError directly, AD-1), verified without
    # needing real Postgres for this case.
    u1 = _make_user(mobile="+8801700001008")
    u2 = _make_user(mobile="+8801700001009")

    class FakeIntegrityError(Exception):
        pass

    deliveries = FakeNotificationDeliveryRepository(fail_bulk_create_with=FakeIntegrityError())
    service, _, deliveries, _ = _service([u1, u2], {u1.id, u2.id}, deliveries=deliveries)

    first = await service.run_daily_report(_TODAY, _NOW)
    assert first.outcome == ScheduledReportOutcome.SUCCEEDED
    assert len(deliveries.bulk_created) == 2

    second = await service.run_daily_report(_TODAY, _NOW)

    assert second.outcome == ScheduledReportOutcome.SKIPPED
    # No rows added on top of the first run's two — the failed second
    # bulk_create call contributed nothing.
    assert len(deliveries.bulk_created) == 2
