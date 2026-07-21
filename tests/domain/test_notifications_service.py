import uuid
from datetime import UTC, datetime

import pytest

from domain.models import (
    AuditLogEntry,
    DeliveryStatus,
    MessageTemplate,
    Notification,
    NotificationDelivery,
    NotificationStatusSummary,
    NotificationTarget,
    NotificationType,
    RecipientList,
    RecipientListKind,
    RecipientListStatus,
    Role,
    TargetType,
    Team,
    TeamStatus,
    User,
    UserStatus,
)
from domain.notifications import (
    InvalidVariableValues,
    ManualNotificationService,
    NoRecipientsSelected,
    NotificationStatusService,
    RecipientResolutionService,
    TemplateNotFound,
)
from ports.whatsapp import SendResult, WhatsAppSendError

# Mirrors adapters/persistence/notifications.py's _STATUS_SEVERITY ranking.
_STATUS_SEVERITY: dict[DeliveryStatus, int] = {
    DeliveryStatus.FAILED: 4,
    DeliveryStatus.FAILED_RETRYABLE: 4,
    DeliveryStatus.RETRYING: 3,
    DeliveryStatus.QUEUED: 2,
    DeliveryStatus.SENDING: 2,
    DeliveryStatus.DELIVERED: 1,
}


def _make_user(
    mobile: str | None = "+8801700000000",
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
        team_id=team_id or uuid.uuid4(),
    )


def _make_template(variable_slots: list[str] | None = None) -> MessageTemplate:
    slots = variable_slots if variable_slots is not None else ["team_name", "new_target"]
    return MessageTemplate(
        id=uuid.uuid4(),
        name="Target Revision Notice",
        twilio_content_sid="HXabc123",
        variable_slots=slots,
        body_preview_template="{team_name}: {new_target}" if slots else "Static body",
        created_at=datetime.now(UTC),
    )


class FakeUserRepository:
    def __init__(self, users: list[User] | None = None) -> None:
        self._by_id = {u.id: u for u in (users or [])}

    async def get_many_by_ids(self, user_ids: list[uuid.UUID]) -> list[User]:
        return [self._by_id[uid] for uid in user_ids if uid in self._by_id]

    async def list_by_team_id(self, team_id: uuid.UUID) -> list[User]:
        return [u for u in self._by_id.values() if u.team_id == team_id]


class FakeRecipientListRepository:
    def __init__(
        self,
        members_by_list: dict[uuid.UUID, list[uuid.UUID]] | None = None,
        inactive_list_ids: set[uuid.UUID] | None = None,
    ) -> None:
        self._members_by_list = members_by_list or {}
        self._inactive = inactive_list_ids or set()

    async def get_member_user_ids(self, recipient_list_id: uuid.UUID) -> list[uuid.UUID]:
        return self._members_by_list.get(recipient_list_id, [])

    async def get_by_id(self, recipient_list_id: uuid.UUID) -> RecipientList:
        status = (
            RecipientListStatus.INACTIVE
            if recipient_list_id in self._inactive
            else RecipientListStatus.ACTIVE
        )
        return RecipientList(
            id=recipient_list_id,
            name="List",
            kind=RecipientListKind.GROUP,
            status=status,
            version=1,
            member_user_ids=self._members_by_list.get(recipient_list_id, []),
        )


class FakeTeamRepository:
    def __init__(self, inactive_team_ids: set[uuid.UUID] | None = None) -> None:
        self._inactive = inactive_team_ids or set()

    async def get_by_id(self, team_id: uuid.UUID) -> Team:
        status = TeamStatus.INACTIVE if team_id in self._inactive else TeamStatus.ACTIVE
        return Team(id=team_id, name="Team", status=status, version=1)


class FakeOptInConsentRepository:
    def __init__(self, opted_in_user_ids: set[uuid.UUID] | None = None) -> None:
        self._opted_in = opted_in_user_ids or set()

    async def get_active_by_user_ids(self, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, object]:
        return {uid: object() for uid in user_ids if uid in self._opted_in}


class FakeMessageTemplateRepository:
    def __init__(self, templates: list[MessageTemplate] | None = None) -> None:
        self._by_id = {t.id: t for t in (templates or [])}

    async def get_by_id(self, template_id: uuid.UUID) -> MessageTemplate | None:
        return self._by_id.get(template_id)


class FakeNotificationRepository:
    def __init__(self) -> None:
        self.added: list[tuple[Notification, list[NotificationTarget]]] = []

    async def add(self, notification: Notification, targets: list[NotificationTarget]) -> None:
        self.added.append((notification, targets))


class FakeNotificationDeliveryRepository:
    def __init__(self, always_fail_claim_for: set[uuid.UUID] | None = None) -> None:
        self._always_fail_claim_for = always_fail_claim_for or set()
        self.bulk_created: list[NotificationDelivery] = []
        self._by_id: dict[uuid.UUID, NotificationDelivery] = {}
        self.updated: list[tuple] = []

    async def bulk_create(self, rows: list[NotificationDelivery]) -> None:
        self.bulk_created.extend(rows)
        for row in rows:
            self._by_id[row.id] = row

    async def claim_for_dispatch(self, delivery_id: uuid.UUID) -> bool:
        if delivery_id in self._always_fail_claim_for:
            return False
        row = self._by_id.get(delivery_id)
        if row is None or row.status not in (
            DeliveryStatus.QUEUED,
            DeliveryStatus.FAILED_RETRYABLE,
        ):
            return False
        row.status = DeliveryStatus.SENDING
        return True

    async def update_after_send(
        self,
        delivery_id: uuid.UUID,
        status: DeliveryStatus,
        provider_message_sid: str | None,
        failure_reason: str | None,
    ) -> None:
        self.updated.append((delivery_id, status, provider_message_sid, failure_reason))
        row = self._by_id.get(delivery_id)
        if row is not None:
            row.status = status
            row.provider_message_sid = provider_message_sid
            row.failure_reason = failure_reason

    async def most_recent_status_summary(self) -> NotificationStatusSummary | None:
        if not self._by_id:
            return None
        # Mirrors the real adapter's worst-status-wins aggregation (AC #8):
        # find the most-recently-created Notification (proxied here by its
        # earliest-created delivery batch, since rows are bulk-created
        # together), then surface the worst status among its own rows.
        latest_row = max(self._by_id.values(), key=lambda row: row.created_at)
        latest_notification_id = latest_row.notification_id
        rows = [
            row for row in self._by_id.values() if row.notification_id == latest_notification_id
        ]
        worst = max(rows, key=lambda row: (_STATUS_SEVERITY[row.status], row.updated_at))
        return NotificationStatusSummary(
            status=worst.status, updated_at=max(row.updated_at for row in rows)
        )


class FakeAuditLogRepository:
    def __init__(self) -> None:
        self.entries: list[AuditLogEntry] = []

    async def add(self, entry: AuditLogEntry) -> None:
        self.entries.append(entry)


class FakeWhatsAppSender:
    def __init__(self, fail_for: set[str] | None = None) -> None:
        self._fail_for = fail_for or set()
        self.sent: list[tuple[str, str, dict]] = []

    async def send_template_message(
        self, to_number: str, content_sid: str, content_variables: dict[str, str]
    ) -> SendResult:
        self.sent.append((to_number, content_sid, content_variables))
        if to_number in self._fail_for:
            raise WhatsAppSendError(code="21610", message="21610: recipient opted out")
        return SendResult(provider_message_sid=f"SM-{to_number}")


def _resolution_service(
    users: FakeUserRepository,
    recipient_lists: FakeRecipientListRepository | None = None,
    consents: FakeOptInConsentRepository | None = None,
    teams: FakeTeamRepository | None = None,
) -> RecipientResolutionService:
    return RecipientResolutionService(
        users,
        recipient_lists or FakeRecipientListRepository(),
        consents or FakeOptInConsentRepository(),
        teams or FakeTeamRepository(),
    )


# --- RecipientResolutionService.resolve ---------------------------------------


async def test_resolve_dedupes_across_user_team_and_recipient_list_overlaps():
    team_id = uuid.uuid4()
    list_id = uuid.uuid4()
    u1 = _make_user(mobile="+8801700000101", team_id=team_id)
    u2 = _make_user(mobile="+8801700000102", team_id=team_id)
    u3 = _make_user(mobile="+8801700000103", team_id=team_id)
    users = FakeUserRepository([u1, u2, u3])
    recipient_lists = FakeRecipientListRepository({list_id: [u2.id]})
    consents = FakeOptInConsentRepository({u1.id, u2.id, u3.id})
    service = _resolution_service(users, recipient_lists, consents)

    resolved = await service.resolve(
        user_ids=[u1.id], team_ids=[team_id], recipient_list_ids=[list_id]
    )

    # selected_count: 1 (direct u1) + 3 (team expand u1,u2,u3) + 1 (list expand u2) = 5
    assert resolved.selected_count == 5
    assert resolved.overlap_count == 2
    assert resolved.ineligible_count == 0
    assert resolved.unique_count == 3
    assert set(resolved.recipient_user_ids) == {u1.id, u2.id, u3.id}


async def test_resolve_tracks_ineligible_separately_from_overlap():
    inactive = _make_user(mobile="+8801700000201", status=UserStatus.INACTIVE)
    not_opted_in = _make_user(mobile="+8801700000202")
    eligible = _make_user(mobile="+8801700000203")
    users = FakeUserRepository([inactive, not_opted_in, eligible])
    consents = FakeOptInConsentRepository({inactive.id, eligible.id})
    service = _resolution_service(users, consents=consents)

    resolved = await service.resolve(
        user_ids=[inactive.id, not_opted_in.id, eligible.id], team_ids=[], recipient_list_ids=[]
    )

    assert resolved.selected_count == 3
    assert resolved.overlap_count == 0
    assert resolved.ineligible_count == 2
    assert resolved.unique_count == 1
    assert resolved.recipient_user_ids == [eligible.id]


async def test_resolve_with_no_selections_returns_all_zero():
    service = _resolution_service(FakeUserRepository())

    resolved = await service.resolve(user_ids=[], team_ids=[], recipient_list_ids=[])

    assert resolved.selected_count == 0
    assert resolved.overlap_count == 0
    assert resolved.ineligible_count == 0
    assert resolved.unique_count == 0
    assert resolved.recipient_user_ids == []


async def test_resolve_excludes_an_active_consented_user_with_no_mobile_number():
    # An Administrator (or any User row with mobile=None) must never be
    # counted as sendable, even though it's active and opted in — sending
    # to "whatsapp:None" would otherwise reach Twilio.
    no_mobile = _make_user(mobile=None)
    with_mobile = _make_user(mobile="+8801700000211")
    users = FakeUserRepository([no_mobile, with_mobile])
    consents = FakeOptInConsentRepository({no_mobile.id, with_mobile.id})
    service = _resolution_service(users, consents=consents)

    resolved = await service.resolve(
        user_ids=[no_mobile.id, with_mobile.id], team_ids=[], recipient_list_ids=[]
    )

    assert resolved.ineligible_count == 1
    assert resolved.unique_count == 1
    assert resolved.recipient_user_ids == [with_mobile.id]


async def test_resolve_skips_expansion_of_an_inactive_team():
    team_id = uuid.uuid4()
    member = _make_user(mobile="+8801700000212", team_id=team_id)
    users = FakeUserRepository([member])
    consents = FakeOptInConsentRepository({member.id})
    teams = FakeTeamRepository(inactive_team_ids={team_id})
    service = _resolution_service(users, consents=consents, teams=teams)

    resolved = await service.resolve(user_ids=[], team_ids=[team_id], recipient_list_ids=[])

    assert resolved.selected_count == 0
    assert resolved.unique_count == 0
    assert resolved.recipient_user_ids == []


async def test_resolve_skips_expansion_of_an_inactive_recipient_list():
    list_id = uuid.uuid4()
    member = _make_user(mobile="+8801700000213")
    users = FakeUserRepository([member])
    consents = FakeOptInConsentRepository({member.id})
    recipient_lists = FakeRecipientListRepository(
        {list_id: [member.id]}, inactive_list_ids={list_id}
    )
    service = _resolution_service(users, recipient_lists=recipient_lists, consents=consents)

    resolved = await service.resolve(user_ids=[], team_ids=[], recipient_list_ids=[list_id])

    assert resolved.selected_count == 0
    assert resolved.unique_count == 0
    assert resolved.recipient_user_ids == []


# --- ManualNotificationService.compose_and_send --------------------------------


def _manual_service(
    users: FakeUserRepository,
    templates: FakeMessageTemplateRepository,
    deliveries: FakeNotificationDeliveryRepository | None = None,
    whatsapp: FakeWhatsAppSender | None = None,
    recipient_lists: FakeRecipientListRepository | None = None,
    consents: FakeOptInConsentRepository | None = None,
) -> tuple[
    ManualNotificationService,
    FakeNotificationRepository,
    FakeNotificationDeliveryRepository,
    FakeAuditLogRepository,
]:
    notifications = FakeNotificationRepository()
    deliveries = deliveries or FakeNotificationDeliveryRepository()
    audit_log = FakeAuditLogRepository()
    resolution = _resolution_service(users, recipient_lists, consents)
    service = ManualNotificationService(
        templates=templates,
        notifications=notifications,
        deliveries=deliveries,
        users=users,
        whatsapp=whatsapp or FakeWhatsAppSender(),
        resolution=resolution,
        audit_log=audit_log,
    )
    return service, notifications, deliveries, audit_log


async def test_compose_and_send_succeeds_creates_rows_and_writes_a_co_transactional_audit_entry():
    u1 = _make_user(mobile="+8801700000301")
    u2 = _make_user(mobile="+8801700000302")
    users = FakeUserRepository([u1, u2])
    consents = FakeOptInConsentRepository({u1.id, u2.id})
    template = _make_template(["team_name", "new_target"])
    templates = FakeMessageTemplateRepository([template])
    service, notifications, deliveries, audit_log = _manual_service(
        users, templates, consents=consents
    )
    actor_id = uuid.uuid4()

    result = await service.compose_and_send(
        template_id=template.id,
        variable_values={"team_name": "Team B", "new_target": "65 Cr BDT"},
        user_ids=[u1.id, u2.id],
        team_ids=[],
        recipient_list_ids=[],
        actor_user_id=actor_id,
    )

    assert len(notifications.added) == 1
    notification, targets = notifications.added[0]
    assert notification.notification_type == NotificationType.MANUAL
    assert notification.created_by_user_id == actor_id
    assert {t.target_id for t in targets} == {u1.id, u2.id}
    assert all(t.target_type == TargetType.USER for t in targets)

    assert len(deliveries.bulk_created) == 2
    assert all(row.notification_type == NotificationType.MANUAL for row in deliveries.bulk_created)
    assert all(row.notification_id == notification.id for row in deliveries.bulk_created)

    assert len(audit_log.entries) == 1
    assert audit_log.entries[0].action == "notification.sent"
    assert audit_log.entries[0].entity_id == notification.id
    assert audit_log.entries[0].actor_user_id == actor_id

    assert {o.status for o in result.outcomes} == {DeliveryStatus.SENDING}
    assert result.notification_id == notification.id


async def test_compose_and_send_records_the_raw_team_target_not_expanded_members():
    team_id = uuid.uuid4()
    u1 = _make_user(mobile="+8801700000303", team_id=team_id)
    u2 = _make_user(mobile="+8801700000304", team_id=team_id)
    users = FakeUserRepository([u1, u2])
    consents = FakeOptInConsentRepository({u1.id, u2.id})
    template = _make_template([])
    templates = FakeMessageTemplateRepository([template])
    service, notifications, _, _ = _manual_service(users, templates, consents=consents)

    await service.compose_and_send(
        template_id=template.id,
        variable_values={},
        user_ids=[],
        team_ids=[team_id],
        recipient_list_ids=[],
        actor_user_id=uuid.uuid4(),
    )

    _, targets = notifications.added[0]
    assert len(targets) == 1
    assert targets[0].target_type == TargetType.TEAM
    assert targets[0].target_id == team_id


async def test_compose_and_send_with_zero_eligible_recipients_raises_no_recipients_selected():
    inactive = _make_user(mobile="+8801700000305", status=UserStatus.INACTIVE)
    users = FakeUserRepository([inactive])
    template = _make_template([])
    templates = FakeMessageTemplateRepository([template])
    service, notifications, deliveries, audit_log = _manual_service(users, templates)

    with pytest.raises(NoRecipientsSelected):
        await service.compose_and_send(
            template_id=template.id,
            variable_values={},
            user_ids=[inactive.id],
            team_ids=[],
            recipient_list_ids=[],
            actor_user_id=uuid.uuid4(),
        )

    assert notifications.added == []
    assert deliveries.bulk_created == []
    assert audit_log.entries == []


async def test_compose_and_send_with_an_unknown_template_raises_template_not_found():
    users = FakeUserRepository()
    templates = FakeMessageTemplateRepository()
    service, *_ = _manual_service(users, templates)

    with pytest.raises(TemplateNotFound):
        await service.compose_and_send(
            template_id=uuid.uuid4(),
            variable_values={},
            user_ids=[],
            team_ids=[],
            recipient_list_ids=[],
            actor_user_id=uuid.uuid4(),
        )


async def test_compose_and_send_with_mismatched_variable_keys_raises_invalid_variable_values():
    u1 = _make_user(mobile="+8801700000306")
    users = FakeUserRepository([u1])
    consents = FakeOptInConsentRepository({u1.id})
    template = _make_template(["team_name", "new_target"])
    templates = FakeMessageTemplateRepository([template])
    service, notifications, *_ = _manual_service(users, templates, consents=consents)

    with pytest.raises(InvalidVariableValues):
        await service.compose_and_send(
            template_id=template.id,
            variable_values={"team_name": "Team B"},  # missing new_target
            user_ids=[u1.id],
            team_ids=[],
            recipient_list_ids=[],
            actor_user_id=uuid.uuid4(),
        )

    assert notifications.added == []


async def test_compose_and_send_rejects_blank_variable_values():
    u1 = _make_user(mobile="+8801700000320")
    users = FakeUserRepository([u1])
    consents = FakeOptInConsentRepository({u1.id})
    template = _make_template(["team_name", "new_target"])
    templates = FakeMessageTemplateRepository([template])
    service, notifications, *_ = _manual_service(users, templates, consents=consents)

    with pytest.raises(InvalidVariableValues):
        await service.compose_and_send(
            template_id=template.id,
            variable_values={"team_name": "Team B", "new_target": "   "},  # whitespace only
            user_ids=[u1.id],
            team_ids=[],
            recipient_list_ids=[],
            actor_user_id=uuid.uuid4(),
        )

    assert notifications.added == []


async def test_compose_and_send_a_whatsapp_failure_is_recorded_as_failed_not_raised():
    ok_user = _make_user(mobile="+8801700000307")
    fails_user = _make_user(mobile="+8801700000308")
    users = FakeUserRepository([ok_user, fails_user])
    consents = FakeOptInConsentRepository({ok_user.id, fails_user.id})
    template = _make_template([])
    templates = FakeMessageTemplateRepository([template])
    whatsapp = FakeWhatsAppSender(fail_for={fails_user.mobile})
    service, _, deliveries, _ = _manual_service(
        users, templates, whatsapp=whatsapp, consents=consents
    )

    result = await service.compose_and_send(
        template_id=template.id,
        variable_values={},
        user_ids=[ok_user.id, fails_user.id],
        team_ids=[],
        recipient_list_ids=[],
        actor_user_id=uuid.uuid4(),
    )

    outcomes_by_user = {o.recipient_user_id: o for o in result.outcomes}
    assert outcomes_by_user[ok_user.id].status == DeliveryStatus.SENDING
    assert outcomes_by_user[ok_user.id].failure_reason is None
    assert outcomes_by_user[fails_user.id].status == DeliveryStatus.FAILED
    assert outcomes_by_user[fails_user.id].failure_reason == "21610: recipient opted out"

    statuses = {row.recipient_user_id: row.status for row in deliveries._by_id.values()}
    assert statuses[ok_user.id] == DeliveryStatus.SENDING
    assert statuses[fails_user.id] == DeliveryStatus.FAILED


async def test_compose_and_send_an_unexpected_transport_error_is_recorded_as_failed_not_raised():
    # Regression: only WhatsAppSendError used to be caught per-recipient —
    # any other exception (timeout, connection error) escaped the loop and,
    # since the whole request is one uncommitted transaction, would have
    # rolled back every already-recorded outcome for recipients processed
    # so far, even though some may have already received a real message.
    ok_user = _make_user(mobile="+8801700000321")
    crashes_user = _make_user(mobile="+8801700000322")
    users = FakeUserRepository([ok_user, crashes_user])
    consents = FakeOptInConsentRepository({ok_user.id, crashes_user.id})
    template = _make_template([])
    templates = FakeMessageTemplateRepository([template])

    class FlakyWhatsAppSender(FakeWhatsAppSender):
        async def send_template_message(
            self, to_number: str, content_sid: str, content_variables: dict
        ) -> SendResult:
            if to_number == crashes_user.mobile:
                raise TimeoutError("connection timed out")
            return await super().send_template_message(to_number, content_sid, content_variables)

    whatsapp = FlakyWhatsAppSender()
    service, _, deliveries, _ = _manual_service(
        users, templates, whatsapp=whatsapp, consents=consents
    )

    result = await service.compose_and_send(
        template_id=template.id,
        variable_values={},
        user_ids=[ok_user.id, crashes_user.id],
        team_ids=[],
        recipient_list_ids=[],
        actor_user_id=uuid.uuid4(),
    )

    outcomes_by_user = {o.recipient_user_id: o for o in result.outcomes}
    assert outcomes_by_user[ok_user.id].status == DeliveryStatus.SENDING
    assert outcomes_by_user[crashes_user.id].status == DeliveryStatus.FAILED
    assert outcomes_by_user[crashes_user.id].failure_reason == "connection timed out"


async def test_compose_and_send_skips_a_delivery_whose_claim_lost_the_race():
    u1 = _make_user(mobile="+8801700000309")
    u2 = _make_user(mobile="+8801700000310")
    users = FakeUserRepository([u1, u2])
    consents = FakeOptInConsentRepository({u1.id, u2.id})
    template = _make_template([])
    templates = FakeMessageTemplateRepository([template])
    whatsapp = FakeWhatsAppSender()

    # The delivery row id isn't known ahead of time (assigned inside
    # compose_and_send), so simulate the race generically: every claim
    # attempt for u2's eventual row will be told "already claimed" by
    # forcing FakeNotificationDeliveryRepository to fail every claim whose
    # row's recipient is u2. Simplest expression: fail claim for the
    # *second* row bulk_create ever receives.
    class RacingDeliveryRepository(FakeNotificationDeliveryRepository):
        async def bulk_create(self, rows):  # type: ignore[override]
            await super().bulk_create(rows)
            for row in rows:
                if row.recipient_user_id == u2.id:
                    self._always_fail_claim_for.add(row.id)

    deliveries = RacingDeliveryRepository()
    service, _, _, _ = _manual_service(
        users, templates, deliveries=deliveries, whatsapp=whatsapp, consents=consents
    )

    result = await service.compose_and_send(
        template_id=template.id,
        variable_values={},
        user_ids=[u1.id, u2.id],
        team_ids=[],
        recipient_list_ids=[],
        actor_user_id=uuid.uuid4(),
    )

    assert len(result.outcomes) == 1
    assert result.outcomes[0].recipient_user_id == u1.id
    assert len(whatsapp.sent) == 1


# --- NotificationStatusService -------------------------------------------------


async def test_latest_notification_status_returns_none_when_nothing_sent_yet():
    service = NotificationStatusService(FakeNotificationDeliveryRepository())

    assert await service.latest_notification_status() is None


async def test_latest_notification_status_reflects_the_most_recently_created_notification():
    deliveries = FakeNotificationDeliveryRepository()
    older = NotificationDelivery(
        id=uuid.uuid4(),
        notification_id=uuid.uuid4(),
        notification_type=NotificationType.MANUAL,
        recipient_user_id=uuid.uuid4(),
        operational_day=None,
        status=DeliveryStatus.SENDING,
        attempt_count=1,
        provider_message_sid="SM-1",
        failure_reason=None,
        created_at=datetime(2026, 7, 20, tzinfo=UTC),
        updated_at=datetime(2026, 7, 20, tzinfo=UTC),
    )
    newer = NotificationDelivery(
        id=uuid.uuid4(),
        notification_id=uuid.uuid4(),
        notification_type=NotificationType.MANUAL,
        recipient_user_id=uuid.uuid4(),
        operational_day=None,
        status=DeliveryStatus.FAILED,
        attempt_count=1,
        provider_message_sid=None,
        failure_reason="21610: recipient opted out",
        created_at=datetime(2026, 7, 21, tzinfo=UTC),
        updated_at=datetime(2026, 7, 21, tzinfo=UTC),
    )
    await deliveries.bulk_create([older, newer])
    service = NotificationStatusService(deliveries)

    latest = await service.latest_notification_status()

    assert latest is not None
    assert latest.status == DeliveryStatus.FAILED
    assert latest.updated_at == newer.updated_at


async def test_latest_notification_status_is_worst_status_across_that_notifications_deliveries():
    # Regression for AC #8: a mostly-successful send with one late failure
    # must not be hidden by whichever recipient happened to be processed
    # last, and a mostly-failed send must not be hidden by a late success.
    deliveries = FakeNotificationDeliveryRepository()
    notification_id = uuid.uuid4()
    succeeded = NotificationDelivery(
        id=uuid.uuid4(),
        notification_id=notification_id,
        notification_type=NotificationType.MANUAL,
        recipient_user_id=uuid.uuid4(),
        operational_day=None,
        status=DeliveryStatus.SENDING,
        attempt_count=1,
        provider_message_sid="SM-1",
        failure_reason=None,
        created_at=datetime(2026, 7, 21, 9, tzinfo=UTC),
        updated_at=datetime(2026, 7, 21, 9, tzinfo=UTC),
    )
    failed = NotificationDelivery(
        id=uuid.uuid4(),
        notification_id=notification_id,
        notification_type=NotificationType.MANUAL,
        recipient_user_id=uuid.uuid4(),
        operational_day=None,
        status=DeliveryStatus.FAILED,
        attempt_count=1,
        provider_message_sid=None,
        failure_reason="21610: recipient opted out",
        created_at=datetime(2026, 7, 21, 9, tzinfo=UTC),
        updated_at=datetime(2026, 7, 21, 9, 1, tzinfo=UTC),
    )
    await deliveries.bulk_create([succeeded, failed])
    service = NotificationStatusService(deliveries)

    latest = await service.latest_notification_status()

    assert latest is not None
    assert latest.status == DeliveryStatus.FAILED
