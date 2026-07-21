"""Manual Notification compose/send (Story 4.1, CAP-4).

``RecipientResolutionService.resolve`` is the one function AD-2 requires be
shared by both the send path (``ManualNotificationService.compose_and_send``)
and the composer's live-preview endpoint — both call sites must see
identical resolution output, so the live preview never promises a bigger
number than what actually gets sent.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from domain.models import (
    AuditLogEntry,
    DeliveryStatus,
    Notification,
    NotificationDelivery,
    NotificationStatusSummary,
    NotificationTarget,
    NotificationType,
    RecipientListStatus,
    TargetType,
    TeamStatus,
    UserStatus,
)
from ports.audit import AuditLogRepository
from ports.consent import OptInConsentRepository
from ports.notifications import (
    MessageTemplateRepository,
    NotificationDeliveryRepository,
    NotificationRepository,
)
from ports.recipient_lists import RecipientListRepository
from ports.teams import TeamRepository
from ports.users import UserRepository
from ports.whatsapp import WhatsAppSender, WhatsAppSendError


class TemplateNotFound(Exception):
    """Raised when no MessageTemplate exists for a given id."""


class InvalidVariableValues(Exception):
    """Raised when the composed message's variable values don't exactly
    match the template's variable_slots (missing or extra keys) — enforces
    AC #4's "variable slots only, no free-form body text"."""


class NoRecipientsSelected(Exception):
    """Raised when recipient resolution yields zero sendable recipients
    (AC #2) — mapped to a 422 by the route."""


@dataclass
class ResolvedRecipients:
    # Raw picker selections/expansions before any filtering.
    selected_count: int
    # Cross-mechanism duplicates only (e.g. individually listed AND a member
    # of a selected Team) — never conflated with ineligible_count.
    overlap_count: int
    # Resolved-but-excluded for being inactive or not opt-in-consented.
    ineligible_count: int
    # Final sendable count: selected_count - overlap_count - ineligible_count.
    unique_count: int
    recipient_user_ids: list[uuid.UUID]


class RecipientResolutionService:
    def __init__(
        self,
        users: UserRepository,
        recipient_lists: RecipientListRepository,
        consents: OptInConsentRepository,
        teams: TeamRepository,
    ) -> None:
        self._users = users
        self._recipient_lists = recipient_lists
        self._consents = consents
        self._teams = teams

    async def resolve(
        self,
        user_ids: list[uuid.UUID],
        team_ids: list[uuid.UUID],
        recipient_list_ids: list[uuid.UUID],
    ) -> ResolvedRecipients:
        expanded_ids: list[uuid.UUID] = list(user_ids)
        for team_id in team_ids:
            # A Team the frontend picker would never offer (it filters to
            # active-only) can still reach here via stale client state or a
            # direct API call — never expand a since-archived Team's
            # members as sendable.
            team = await self._teams.get_by_id(team_id)
            if team is None or team.status != TeamStatus.ACTIVE:
                continue
            members = await self._users.list_by_team_id(team_id)
            expanded_ids.extend(member.id for member in members)
        for recipient_list_id in recipient_list_ids:
            recipient_list = await self._recipient_lists.get_by_id(recipient_list_id)
            if recipient_list is None or recipient_list.status != RecipientListStatus.ACTIVE:
                continue
            expanded_ids.extend(recipient_list.member_user_ids)

        selected_count = len(expanded_ids)
        deduped_ids = list(dict.fromkeys(expanded_ids))
        overlap_count = selected_count - len(deduped_ids)

        resolved_users = await self._users.get_many_by_ids(deduped_ids)
        users_by_id = {user.id: user for user in resolved_users}
        active_consent_by_user = await self._consents.get_active_by_user_ids(deduped_ids)

        sendable_ids: list[uuid.UUID] = []
        ineligible_count = 0
        for user_id in deduped_ids:
            user = users_by_id.get(user_id)
            if (
                user is None
                or user.status != UserStatus.ACTIVE
                or user.mobile is None
                or user_id not in active_consent_by_user
            ):
                ineligible_count += 1
                continue
            sendable_ids.append(user_id)

        return ResolvedRecipients(
            selected_count=selected_count,
            overlap_count=overlap_count,
            ineligible_count=ineligible_count,
            unique_count=len(sendable_ids),
            recipient_user_ids=sendable_ids,
        )


@dataclass
class DeliveryOutcome:
    recipient_user_id: uuid.UUID
    # Only "sending" (accepted by Twilio) or "failed" (rejected, terminal)
    # are produced here — delivered/retrying are Story 4.3's webhook-driven
    # transitions.
    status: DeliveryStatus
    failure_reason: str | None


@dataclass
class ComposeResult:
    notification_id: uuid.UUID
    outcomes: list[DeliveryOutcome]


class ManualNotificationService:
    def __init__(
        self,
        templates: MessageTemplateRepository,
        notifications: NotificationRepository,
        deliveries: NotificationDeliveryRepository,
        users: UserRepository,
        whatsapp: WhatsAppSender,
        resolution: RecipientResolutionService,
        audit_log: AuditLogRepository,
    ) -> None:
        self._templates = templates
        self._notifications = notifications
        self._deliveries = deliveries
        self._users = users
        self._whatsapp = whatsapp
        self._resolution = resolution
        self._audit_log = audit_log

    async def compose_and_send(
        self,
        template_id: uuid.UUID,
        variable_values: dict[str, str],
        user_ids: list[uuid.UUID],
        team_ids: list[uuid.UUID],
        recipient_list_ids: list[uuid.UUID],
        actor_user_id: uuid.UUID,
    ) -> ComposeResult:
        template = await self._templates.get_by_id(template_id)
        if template is None:
            raise TemplateNotFound()

        if set(variable_values.keys()) != set(template.variable_slots):
            raise InvalidVariableValues()
        if any(not value.strip() for value in variable_values.values()):
            raise InvalidVariableValues()

        resolved = await self._resolution.resolve(user_ids, team_ids, recipient_list_ids)
        if resolved.unique_count == 0:
            raise NoRecipientsSelected()

        now = datetime.now(UTC)
        notification = Notification(
            id=uuid.uuid4(),
            notification_type=NotificationType.MANUAL,
            template_id=template_id,
            created_by_user_id=actor_user_id,
            created_at=now,
        )
        # The raw picker selections, not the expanded members (AD-4).
        targets = [
            NotificationTarget(
                id=uuid.uuid4(),
                notification_id=notification.id,
                target_type=TargetType.USER,
                target_id=user_id,
            )
            for user_id in user_ids
        ] + [
            NotificationTarget(
                id=uuid.uuid4(),
                notification_id=notification.id,
                target_type=TargetType.TEAM,
                target_id=team_id,
            )
            for team_id in team_ids
        ] + [
            NotificationTarget(
                id=uuid.uuid4(),
                notification_id=notification.id,
                target_type=TargetType.RECIPIENT_LIST,
                target_id=recipient_list_id,
            )
            for recipient_list_id in recipient_list_ids
        ]

        await self._notifications.add(notification, targets)
        await self._audit_log.add(
            AuditLogEntry(
                id=uuid.uuid4(),
                actor_user_id=actor_user_id,
                action="notification.sent",
                entity_type="Notification",
                entity_id=notification.id,
                details={
                    "template_id": str(template_id),
                    "recipient_count": resolved.unique_count,
                },
                created_at=now,
            )
        )

        delivery_rows = [
            NotificationDelivery(
                id=uuid.uuid4(),
                notification_id=notification.id,
                notification_type=NotificationType.MANUAL,
                recipient_user_id=recipient_user_id,
                operational_day=None,
                status=DeliveryStatus.QUEUED,
                attempt_count=0,
                provider_message_sid=None,
                failure_reason=None,
                created_at=now,
                updated_at=now,
            )
            for recipient_user_id in resolved.recipient_user_ids
        ]
        await self._deliveries.bulk_create(delivery_rows)

        recipients_by_id = {
            user.id: user for user in await self._users.get_many_by_ids(resolved.recipient_user_ids)
        }
        # Positional string keys ("1", "2", ...), not named — variable_slots'
        # order is what maps a named slot to Twilio's positional key.
        content_variables = {
            str(index): variable_values[slot]
            for index, slot in enumerate(template.variable_slots, start=1)
        }

        # Small manual-send batch sizes — looped synchronously (Twilio
        # allows 80 msg/sec per sender, far above this path's volume;
        # NFR-1's 500+ concurrent dispatch figure is Story 4.2's scope).
        outcomes: list[DeliveryOutcome] = []

        async def _fail(row: NotificationDelivery, reason: str) -> None:
            # Every per-recipient failure mode — Twilio rejection, a
            # transport/timeout error, or a missing recipient record — must
            # land here rather than propagate: an uncaught exception here
            # would abort the loop, and since this whole request is one
            # uncommitted transaction, that would roll back the
            # already-recorded outcomes (and Notification/audit rows) for
            # every recipient processed so far, even though Twilio may have
            # already sent them a real message.
            await self._deliveries.update_after_send(row.id, DeliveryStatus.FAILED, None, reason)
            outcomes.append(
                DeliveryOutcome(
                    recipient_user_id=row.recipient_user_id,
                    status=DeliveryStatus.FAILED,
                    failure_reason=reason,
                )
            )

        for row in delivery_rows:
            claimed = await self._deliveries.claim_for_dispatch(row.id)
            if not claimed:
                continue  # pragma: no cover - unreachable for a freshly-created row

            recipient = recipients_by_id.get(row.recipient_user_id)
            if recipient is None:
                await _fail(row, "recipient no longer exists")
                continue

            try:
                result = await self._whatsapp.send_template_message(
                    to_number=recipient.mobile,
                    content_sid=template.twilio_content_sid,
                    content_variables=content_variables,
                )
            except WhatsAppSendError as exc:
                await _fail(row, exc.message)
                continue
            except Exception as exc:
                # Deliberately broad: see _fail's docstring above.
                await _fail(row, str(exc))
                continue

            await self._deliveries.update_after_send(
                row.id, DeliveryStatus.SENDING, result.provider_message_sid, None
            )
            outcomes.append(
                DeliveryOutcome(
                    recipient_user_id=row.recipient_user_id,
                    status=DeliveryStatus.SENDING,
                    failure_reason=None,
                )
            )

        return ComposeResult(notification_id=notification.id, outcomes=outcomes)


class NotificationStatusService:
    """Read-only — the Dashboard tile's own dependency footprint, separate
    from ManualNotificationService's write-path dependencies (Twilio, audit
    log) that a read has no business requiring."""

    def __init__(self, deliveries: NotificationDeliveryRepository) -> None:
        self._deliveries = deliveries

    async def latest_notification_status(self) -> NotificationStatusSummary | None:
        # "Most recent send system-wide" (AC #8) — Scheduled doesn't exist
        # yet, so today this is always the latest Manual send. Aggregated
        # worst-status-wins across all of that Notification's deliveries so
        # one late failure/success can't misrepresent the rest.
        return await self._deliveries.most_recent_status_summary()
